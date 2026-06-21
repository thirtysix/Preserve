"""Privacy-preserving wrapper around OpenAI-compatible LLM APIs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from preserve.audit import AuditLog
from preserve.config import PreserveConfig
from preserve.mapping import PlaceholderMap
from preserve.scrubber import Scrubber

# Load .env from the project root (walk up from this file)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"


@dataclass
class PreserveResponse:
    """Response from a privacy-preserving API call."""

    raw_response: str  # Response with placeholders still in place
    restored_response: str  # Response with original PII re-inserted
    placeholder_map: PlaceholderMap
    model: str
    usage: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        """The de-anonymized response text."""
        return self.restored_response


class PreserveClient:
    """OpenAI-compatible client that automatically scrubs PII from queries."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEEPINFRA_BASE_URL,
        config: PreserveConfig | None = None,
    ) -> None:
        self.config = config or PreserveConfig()
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._scrubber = Scrubber(self.config)
        self.audit_log = AuditLog(
            log_scrubbed_content=self.config.log_scrubbed_content
        )

    def chat(
        self,
        messages: list[dict],
        scrub: bool = True,
        **kwargs,
    ) -> PreserveResponse:
        """Send a chat completion request with automatic PII scrubbing.

        Args:
            messages: OpenAI-format messages [{"role": "user", "content": "..."}]
            scrub: Whether to apply PII scrubbing (default True)
            **kwargs: Additional arguments passed to the OpenAI chat completions API
        """
        if scrub:
            sanitized_messages, placeholder_map, detections = (
                self._scrubber.scrub_messages(messages)
            )

            # Record in audit log
            original_text = "\n".join(
                m.get("content", "") for m in messages if isinstance(m.get("content"), str)
            )
            self.audit_log.record(original_text, detections, placeholder_map)
        else:
            sanitized_messages = messages
            placeholder_map = PlaceholderMap()

        # Make the API call
        response = self._client.chat.completions.create(
            model=self.model,
            messages=sanitized_messages,
            **kwargs,
        )

        raw_text = response.choices[0].message.content or ""

        # Restore PII in response
        restored_text = placeholder_map.restore(raw_text) if scrub else raw_text

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return PreserveResponse(
            raw_response=raw_text,
            restored_response=restored_text,
            placeholder_map=placeholder_map,
            model=response.model,
            usage=usage,
        )

    def scrub_only(self, messages: list[dict]) -> tuple[list[dict], PlaceholderMap]:
        """Preview what would be sent without making an API call."""
        sanitized_messages, placeholder_map, _ = self._scrubber.scrub_messages(messages)
        return sanitized_messages, placeholder_map


def create_client(
    api_key: str,
    model: str = "meta-llama/Llama-3.3-70B-Instruct",
    base_url: str = DEEPINFRA_BASE_URL,
    **config_kwargs,
) -> PreserveClient:
    """Convenience factory for creating a PreserveClient."""
    config = PreserveConfig(**config_kwargs)
    return PreserveClient(api_key=api_key, model=model, base_url=base_url, config=config)
