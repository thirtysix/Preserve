"""Preserve API gateway — FastAPI app.

Central, privacy-preserving LLM proxy. Flow for /v1/chat/completions:

    client --(raw text)--> gateway --(scrubbed)--> upstream LLM
    client <--(restored)-- gateway <--(scrubbed)-- upstream LLM

The placeholder map lives only for the duration of the request and is never
persisted. PII never reaches the upstream provider; audit logs store counts,
never values.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

from preserve.api.models import (
    ChatCompletionRequest, DetectRequest, DetectResponse, Detection,
    RestoreRequest, RestoreResponse, ScrubRequest, ScrubResponse,
)
from preserve.api.ratelimit import RateLimitExceeded, get_rate_limiter
from preserve.api.settings import APIKey, APISettings, get_settings
from preserve.config import PreserveConfig, SensitivityLevel
from preserve.mapping import PlaceholderMap
from preserve.scrubber import Scrubber

logger = logging.getLogger("preserve.api")


def create_app(settings: Optional[APISettings] = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Preserve API Gateway",
        version="0.1.0",
        description="Privacy-preserving LLM proxy: scrubs PII before it reaches the upstream model.",
    )
    app.state.settings = settings
    app.state.limiter = get_rate_limiter()
    app.state._scrubbers: dict[str, Scrubber] = {}
    app.state._scrubber_lock = threading.Lock()
    app.state._upstream = None

    audit_path = Path(__file__).resolve().parent.parent.parent / "logs" / "api_audit.jsonl"

    # --- shared helpers -------------------------------------------------
    def get_scrubber(sensitivity: SensitivityLevel) -> Scrubber:
        key = sensitivity.value
        with app.state._scrubber_lock:
            sc = app.state._scrubbers.get(key)
            if sc is None:
                cfg = PreserveConfig(
                    sensitivity_level=sensitivity,
                    use_name_scorer=settings.use_name_scorer,
                    use_llm_review=False,
                    log_scrubbed_content=False,
                )
                sc = Scrubber(cfg)
                app.state._scrubbers[key] = sc
            return sc

    def resolve_sensitivity(override: Optional[str]) -> SensitivityLevel:
        if not override:
            return settings.sensitivity
        try:
            return SensitivityLevel(override.lower())
        except ValueError:
            raise HTTPException(422, f"Invalid sensitivity '{override}'. "
                                     "Use minimal, standard, or aggressive.")

    def upstream_client() -> OpenAI:
        if app.state._upstream is None:
            if not settings.upstream_api_key:
                raise HTTPException(503, "Upstream LLM not configured "
                                         "(set PRESERVE_UPSTREAM_API_KEY).")
            app.state._upstream = OpenAI(
                base_url=settings.upstream_base_url,
                api_key=settings.upstream_api_key,
            )
        return app.state._upstream

    def audit(principal: APIKey, endpoint: str, summary: dict, tokens: int = 0,
              model: str = "") -> None:
        """Append a PII-free usage record."""
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                "ts": round(time.time(), 3),
                "principal": principal.name,
                "endpoint": endpoint,
                "model": model,
                "pii_redacted": sum(summary.values()),
                "by_type": summary,
                "upstream_tokens": tokens,
            }
            with audit_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:  # never let audit failure break a request
            logger.warning("audit write failed: %s", e)

    def require_key(authorization: str = Header(None),
                    x_api_key: str = Header(None)) -> APIKey:
        if settings.allow_no_auth:
            return APIKey(key="dev", name="dev-no-auth", rpm=0, daily_token_quota=0)
        token = x_api_key
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            raise HTTPException(401, "Missing API key (Authorization: Bearer <key> "
                                     "or X-API-Key header).")
        principal = settings.keys.get(token)
        if principal is None:
            raise HTTPException(401, "Invalid API key.")
        return principal

    def enforce_limits(principal: APIKey) -> None:
        app.state.limiter.check_request(principal.key, principal.rpm)
        app.state.limiter.check_token_quota(principal.key, principal.daily_token_quota)

    # --- error handling -------------------------------------------------
    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(_: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"error": {"message": str(exc), "type": "rate_limit_exceeded"}},
            headers={"Retry-After": str(exc.retry_after)},
        )

    # --- routes ---------------------------------------------------------
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "preserve-api", "version": "0.1.0",
                "auth": "disabled" if settings.allow_no_auth else "enabled"}

    @app.post("/v1/chat/completions")
    def chat_completions(req: ChatCompletionRequest,
                         principal: APIKey = Depends(require_key)):
        if req.stream:
            raise HTTPException(400, "Streaming is not supported "
                                     "(PII restoration needs the full response).")
        enforce_limits(principal)

        messages = [m.model_dump(exclude_none=True) for m in req.messages]
        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars > settings.max_input_chars:
            raise HTTPException(413, f"Input exceeds {settings.max_input_chars} characters.")

        sensitivity = settings.sensitivity
        scrubber = get_scrubber(sensitivity)
        sanitized, pmap, detections = scrubber.scrub_messages(messages)
        summary: dict[str, int] = {}
        for d in detections:
            summary[d.replacement_type] = summary.get(d.replacement_type, 0) + 1

        model = req.model or settings.default_model
        try:
            resp = upstream_client().chat.completions.create(
                model=model, messages=sanitized, **req.passthrough_params(),
            )
        except Exception as e:
            logger.warning("upstream error: %s", e)
            raise HTTPException(502, f"Upstream LLM error: {e}")

        data = resp.model_dump()
        # Restore PII in each choice's message content AND any tool/function call
        # arguments (placeholders can appear inside the JSON argument string).
        for choice in data.get("choices", []):
            msg = choice.get("message") or {}
            if isinstance(msg.get("content"), str):
                msg["content"] = pmap.restore(msg["content"])
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function") or {}
                if isinstance(fn.get("arguments"), str):
                    fn["arguments"] = pmap.restore(fn["arguments"])
            fc = msg.get("function_call")
            if isinstance(fc, dict) and isinstance(fc.get("arguments"), str):
                fc["arguments"] = pmap.restore(fc["arguments"])

        tokens = (data.get("usage") or {}).get("total_tokens", 0) or 0
        daily = app.state.limiter.add_tokens(principal.key, tokens)
        audit(principal, "chat_completions", summary, tokens, model)

        data["x_preserve"] = {
            "pii_redacted": sum(summary.values()),
            "by_type": summary,
            "sensitivity": sensitivity.value,
            "daily_tokens_used": daily,
        }
        return data

    @app.post("/v1/scrub", response_model=ScrubResponse)
    def scrub(req: ScrubRequest, principal: APIKey = Depends(require_key)):
        enforce_limits(principal)
        if len(req.text) > settings.max_input_chars:
            raise HTTPException(413, f"Input exceeds {settings.max_input_chars} characters.")
        result = get_scrubber(resolve_sensitivity(req.sensitivity)).scrub(req.text)
        audit(principal, "scrub", result.pii_summary)
        return ScrubResponse(
            sanitized_text=result.sanitized_text,
            placeholder_map=result.placeholder_map.to_dict(),
            pii_summary=result.pii_summary,
            pii_count=result.pii_count,
        )

    @app.post("/v1/restore", response_model=RestoreResponse)
    def restore(req: RestoreRequest, principal: APIKey = Depends(require_key)):
        enforce_limits(principal)
        try:
            pmap = PlaceholderMap.from_dict(req.placeholder_map)
        except Exception:
            raise HTTPException(422, "Invalid placeholder_map (expected the object "
                                     "returned by /v1/scrub).")
        return RestoreResponse(restored_text=pmap.restore(req.text))

    @app.post("/v1/detect", response_model=DetectResponse)
    def detect(req: DetectRequest, principal: APIKey = Depends(require_key)):
        enforce_limits(principal)
        if len(req.text) > settings.max_input_chars:
            raise HTTPException(413, f"Input exceeds {settings.max_input_chars} characters.")
        result = get_scrubber(resolve_sensitivity(req.sensitivity)).scrub(req.text)
        dets = [
            Detection(
                type=d.replacement_type, start=d.start, end=d.end,
                confidence=round(d.confidence, 3), layer=d.detection_layer,
                value=(d.matched_text if req.include_values else None),
            )
            for d in sorted(result.detections, key=lambda x: x.start)
        ]
        audit(principal, "detect", result.pii_summary)
        return DetectResponse(detections=dets, summary=result.pii_summary)

    return app


app = create_app()
