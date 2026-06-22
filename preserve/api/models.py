"""Pydantic request/response schemas for the Preserve API gateway."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- OpenAI-compatible chat completions ---
class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible request. Unknown fields (temperature, top_p, max_tokens,
    stop, …) are allowed and forwarded verbatim to the upstream LLM."""

    model_config = {"extra": "allow"}

    model: Optional[str] = None
    messages: list[ChatMessage]
    stream: bool = False

    def passthrough_params(self) -> dict[str, Any]:
        """Extra fields to forward to the upstream API (everything but the
        fields the gateway handles itself)."""
        handled = {"model", "messages", "stream"}
        extra = dict(self.__pydantic_extra__ or {})
        return {k: v for k, v in extra.items() if k not in handled}


# --- Scrub / restore / detect ---
class ScrubRequest(BaseModel):
    text: str
    sensitivity: Optional[str] = None  # override the gateway default


class ScrubResponse(BaseModel):
    sanitized_text: str
    placeholder_map: dict  # serialized PlaceholderMap (placeholder -> original)
    pii_summary: dict[str, int]
    pii_count: int


class RestoreRequest(BaseModel):
    text: str
    placeholder_map: dict  # the dict returned by /v1/scrub


class RestoreResponse(BaseModel):
    restored_text: str


class DetectRequest(BaseModel):
    text: str
    sensitivity: Optional[str] = None
    include_values: bool = True  # set false to omit the matched PII strings


class Detection(BaseModel):
    type: str
    start: int
    end: int
    confidence: float
    layer: str
    value: Optional[str] = None


class DetectResponse(BaseModel):
    detections: list[Detection]
    summary: dict[str, int]
