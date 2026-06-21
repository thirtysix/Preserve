"""Core PII scrubbing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from preserve.config import PreserveConfig
from preserve.detectors import PIIDetector, PIIMatch
from preserve.mapping import PlaceholderMap


@dataclass
class ScrubResult:
    """Result of a scrubbing operation."""

    sanitized_text: str
    original_text: str
    placeholder_map: PlaceholderMap
    detections: list[PIIMatch] = field(default_factory=list)

    @property
    def pii_found(self) -> bool:
        return len(self.detections) > 0

    @property
    def pii_count(self) -> int:
        return len(self.detections)

    @property
    def pii_summary(self) -> dict[str, int]:
        """Count of detections by type."""
        summary: dict[str, int] = {}
        for d in self.detections:
            summary[d.replacement_type] = summary.get(d.replacement_type, 0) + 1
        return summary


class Scrubber:
    """Detects and replaces PII with reversible placeholders."""

    def __init__(self, config: PreserveConfig | None = None) -> None:
        self.config = config or PreserveConfig()
        self._detector = PIIDetector(self.config)

    def scrub(self, text: str) -> ScrubResult:
        """Detect and replace all PII in text with placeholders."""
        detections = self._detector.detect(text)
        placeholder_map = PlaceholderMap(
            placeholder_format=self.config.placeholder_format
        )

        # Sort by position descending so replacements don't shift offsets
        sorted_detections = sorted(detections, key=lambda d: d.start, reverse=True)

        sanitized = text
        for detection in sorted_detections:
            placeholder = placeholder_map.add(
                detection.matched_text, detection.replacement_type
            )
            sanitized = (
                sanitized[: detection.start]
                + placeholder
                + sanitized[detection.end :]
            )

        return ScrubResult(
            sanitized_text=sanitized,
            original_text=text,
            placeholder_map=placeholder_map,
            detections=detections,
        )

    def scrub_messages(
        self, messages: list[dict]
    ) -> tuple[list[dict], PlaceholderMap, list[PIIMatch]]:
        """Scrub PII from a list of chat messages (OpenAI format).

        Returns (sanitized_messages, combined_placeholder_map, all_detections).
        """
        placeholder_map = PlaceholderMap(
            placeholder_format=self.config.placeholder_format
        )
        all_detections: list[PIIMatch] = []
        sanitized_messages = []

        for msg in messages:
            sanitized_msg = dict(msg)
            if isinstance(msg.get("content"), str):
                detections = self._detector.detect(msg["content"])
                all_detections.extend(detections)

                sorted_detections = sorted(
                    detections, key=lambda d: d.start, reverse=True
                )
                content = msg["content"]
                for detection in sorted_detections:
                    placeholder = placeholder_map.add(
                        detection.matched_text, detection.replacement_type
                    )
                    content = (
                        content[: detection.start]
                        + placeholder
                        + content[detection.end :]
                    )
                sanitized_msg["content"] = content

            sanitized_messages.append(sanitized_msg)

        return sanitized_messages, placeholder_map, all_detections

    @staticmethod
    def restore(text: str, placeholder_map: PlaceholderMap) -> str:
        """Restore original PII values in text using the placeholder map."""
        return placeholder_map.restore(text)
