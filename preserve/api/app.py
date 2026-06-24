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

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
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

        if req.stream:
            from preserve.api.streaming import PlaceholderStreamRestorer
            passthrough = req.passthrough_params()

            def event_stream():
                content_r = PlaceholderStreamRestorer(pmap.restore)
                tool_rs: dict[int, PlaceholderStreamRestorer] = {}
                total_tokens = 0
                chunk_id = "chatcmpl-stream"
                try:
                    stream = upstream_client().chat.completions.create(
                        model=model, messages=sanitized, stream=True, **passthrough,
                    )
                except Exception as e:
                    logger.warning("upstream stream error: %s", e)
                    yield "data: " + json.dumps(
                        {"error": {"message": f"Upstream LLM error: {e}", "type": "upstream_error"}}
                    ) + "\n\n"
                    yield "data: [DONE]\n\n"
                    return
                for chunk in stream:
                    d = chunk.model_dump()
                    chunk_id = d.get("id") or chunk_id
                    for choice in d.get("choices", []):
                        delta = choice.get("delta") or {}
                        if isinstance(delta.get("content"), str):
                            delta["content"] = content_r.feed(delta["content"])
                        for tc in (delta.get("tool_calls") or []):
                            fn = tc.get("function") or {}
                            if isinstance(fn.get("arguments"), str):
                                r = tool_rs.setdefault(
                                    tc.get("index", 0), PlaceholderStreamRestorer(pmap.restore))
                                fn["arguments"] = r.feed(fn["arguments"])
                    u = d.get("usage")
                    if u and u.get("total_tokens"):
                        total_tokens = u["total_tokens"]
                    yield "data: " + json.dumps(d) + "\n\n"
                # Emit any held-back tail (an unfinished placeholder that never completed)
                tail = content_r.flush()
                tool_tails = {i: r.flush() for i, r in tool_rs.items()}
                if tail or any(tool_tails.values()):
                    delta = {}
                    if tail:
                        delta["content"] = tail
                    tcs = [{"index": i, "function": {"arguments": t}}
                           for i, t in tool_tails.items() if t]
                    if tcs:
                        delta["tool_calls"] = tcs
                    yield "data: " + json.dumps({
                        "id": chunk_id, "object": "chat.completion.chunk", "model": model,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) + "\n\n"
                if total_tokens:
                    app.state.limiter.add_tokens(principal.key, total_tokens)
                audit(principal, "chat_completions_stream", summary, total_tokens, model)
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_stream(), media_type="text/event-stream")

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

    @app.post("/v1/messages")
    def anthropic_messages(req: dict = Body(...),
                           principal: APIKey = Depends(require_key)):
        """Anthropic Messages API: scrub -> OpenAI-compatible upstream -> restore,
        returning Anthropic-format content (text + tool_use), streaming or not."""
        enforce_limits(principal)

        def block_text(content) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        parts.append(b.get("text", ""))
                    elif b.get("type") == "tool_result":
                        parts.append(block_text(b.get("content")))
                return "\n".join(p for p in parts if p)
            return ""

        oai_messages = []
        system = req.get("system")
        if system is not None:
            sys_text = block_text(system)
            if sys_text:
                oai_messages.append({"role": "system", "content": sys_text})
        for m in (req.get("messages") or []):
            oai_messages.append({"role": m.get("role", "user"),
                                 "content": block_text(m.get("content"))})

        total_chars = sum(len(m["content"]) for m in oai_messages)
        if total_chars > settings.max_input_chars:
            raise HTTPException(413, f"Input exceeds {settings.max_input_chars} characters.")

        scrubber = get_scrubber(settings.sensitivity)
        sanitized, pmap, detections = scrubber.scrub_messages(oai_messages)
        summary: dict[str, int] = {}
        for d in detections:
            summary[d.replacement_type] = summary.get(d.replacement_type, 0) + 1

        model = req.get("model") or settings.default_model
        params = {}
        for src, dst in (("max_tokens", "max_tokens"), ("temperature", "temperature"),
                         ("top_p", "top_p"), ("stop_sequences", "stop")):
            if req.get(src) is not None:
                params[dst] = req[src]
        stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}

        # ---- streaming: translate the OpenAI-compatible upstream stream into
        # Anthropic SSE events, restoring PII incrementally (hold-back buffer). ----
        if req.get("stream"):
            from preserve.api.streaming import PlaceholderStreamRestorer

            def sse(event, data):
                return f"event: {event}\ndata: {json.dumps(data)}\n\n"

            def event_stream():
                yield sse("message_start", {"type": "message_start", "message": {
                    "id": "msg_stream", "type": "message", "role": "assistant", "content": [],
                    "model": model, "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0}}})
                text_r = PlaceholderStreamRestorer(pmap.restore)
                tool_r = {}
                next_index = 0
                text_idx = None
                tool_idx = {}
                stop_reason = "end_turn"
                out_tokens = 0
                try:
                    stream = upstream_client().chat.completions.create(
                        model=model, messages=sanitized, stream=True, **params)
                except Exception as e:
                    logger.warning("upstream stream error: %s", e)
                    yield sse("error", {"type": "error", "error": {
                        "type": "api_error", "message": f"Upstream LLM error: {e}"}})
                    yield sse("message_stop", {"type": "message_stop"})
                    return
                for chunk in stream:
                    d = chunk.model_dump()
                    for choice in d.get("choices", []):
                        delta = choice.get("delta") or {}
                        if choice.get("finish_reason"):
                            stop_reason = stop_map.get(choice["finish_reason"], "end_turn")
                        c = delta.get("content")
                        if isinstance(c, str) and c:
                            if text_idx is None:
                                text_idx = next_index
                                next_index += 1
                                yield sse("content_block_start", {"type": "content_block_start",
                                    "index": text_idx, "content_block": {"type": "text", "text": ""}})
                            emit = text_r.feed(c)
                            if emit:
                                yield sse("content_block_delta", {"type": "content_block_delta",
                                    "index": text_idx, "delta": {"type": "text_delta", "text": emit}})
                        for tc in (delta.get("tool_calls") or []):
                            oi = tc.get("index", 0)
                            fn = tc.get("function") or {}
                            if oi not in tool_idx:
                                tool_idx[oi] = next_index
                                next_index += 1
                                tool_r[oi] = PlaceholderStreamRestorer(pmap.restore)
                                yield sse("content_block_start", {"type": "content_block_start",
                                    "index": tool_idx[oi], "content_block": {"type": "tool_use",
                                        "id": tc.get("id") or f"toolu_{oi}",
                                        "name": fn.get("name") or "", "input": {}}})
                            args = fn.get("arguments")
                            if isinstance(args, str) and args:
                                emit = tool_r[oi].feed(args)
                                if emit:
                                    yield sse("content_block_delta", {"type": "content_block_delta",
                                        "index": tool_idx[oi],
                                        "delta": {"type": "input_json_delta", "partial_json": emit}})
                    u = d.get("usage")
                    if u and u.get("completion_tokens"):
                        out_tokens = u["completion_tokens"]
                if text_idx is not None:
                    tail = text_r.flush()
                    if tail:
                        yield sse("content_block_delta", {"type": "content_block_delta",
                            "index": text_idx, "delta": {"type": "text_delta", "text": tail}})
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": text_idx})
                for oi, bi in tool_idx.items():
                    tail = tool_r[oi].flush()
                    if tail:
                        yield sse("content_block_delta", {"type": "content_block_delta",
                            "index": bi, "delta": {"type": "input_json_delta", "partial_json": tail}})
                    yield sse("content_block_stop", {"type": "content_block_stop", "index": bi})
                yield sse("message_delta", {"type": "message_delta",
                    "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": out_tokens}})
                app.state.limiter.add_tokens(principal.key, out_tokens)
                audit(principal, "messages_stream", summary, out_tokens, model)
                yield sse("message_stop", {"type": "message_stop"})

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        try:
            resp = upstream_client().chat.completions.create(
                model=model, messages=sanitized, **params,
            )
        except Exception as e:
            logger.warning("upstream error: %s", e)
            raise HTTPException(502, f"Upstream LLM error: {e}")

        data = resp.model_dump()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content_blocks = []
        if isinstance(msg.get("content"), str) and msg["content"]:
            content_blocks.append({"type": "text", "text": pmap.restore(msg["content"])})
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            restored_args = pmap.restore(fn.get("arguments") or "{}")
            try:
                tool_input = json.loads(restored_args)
            except Exception:
                tool_input = {"_raw": restored_args}
            content_blocks.append({"type": "tool_use", "id": tc.get("id") or "toolu_0",
                                   "name": fn.get("name") or "", "input": tool_input})
        if not content_blocks:
            content_blocks.append({"type": "text", "text": ""})

        usage = data.get("usage") or {}
        tokens = usage.get("total_tokens", 0) or 0
        app.state.limiter.add_tokens(principal.key, tokens)
        audit(principal, "messages", summary, tokens, model)
        return {
            "id": data.get("id", "msg"),
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content_blocks,
            "stop_reason": stop_map.get(choice.get("finish_reason"), "end_turn"),
            "stop_sequence": None,
            "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                      "output_tokens": usage.get("completion_tokens", 0)},
            "x_preserve": {"pii_redacted": sum(summary.values()), "by_type": summary},
        }

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
