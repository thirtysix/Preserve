"""Pydantic request/response schemas for the Preserve API gateway."""

from __future__ import annotations

import inspect
from typing import Any, Optional

from openai.resources.chat.completions import Completions
from pydantic import BaseModel, Field

# Keyword arguments chat.completions.create() accepts.
_SDK_PARAMS = set(inspect.signature(Completions.create).parameters) - {"self"}


# --- OpenAI-compatible chat completions ---
class ChatMessage(BaseModel):
    """A chat message. Tool-calling turns are forwarded intact: an assistant
    message may carry ``tool_calls`` with no content, and a ``tool`` message
    carries ``tool_call_id`` (extra fields are kept, not dropped)."""

    model_config = {"extra": "allow"}

    role: str
    content: Optional[str] = None
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
        params = {k: v for k, v in extra.items() if k not in handled}
        # The OpenAI SDK rejects keyword arguments it does not know (provider
        # extensions such as chat_template_kwargs); those go in extra_body,
        # which the SDK merges into the request JSON unchanged.
        body = {k: params.pop(k) for k in list(params) if k not in _SDK_PARAMS}
        if body:
            params["extra_body"] = {**params.get("extra_body", {}), **body}
        return params


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
