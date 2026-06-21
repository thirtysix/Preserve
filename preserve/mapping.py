"""Reversible placeholder mapping for PII scrubbing."""

from __future__ import annotations

from collections import defaultdict


class PlaceholderMap:
    """Bidirectional mapping between original PII values and placeholders."""

    def __init__(self, placeholder_format: str = "[{type}_{id}]") -> None:
        self._format = placeholder_format
        self._original_to_placeholder: dict[str, str] = {}
        self._placeholder_to_original: dict[str, str] = {}
        self._counters: dict[str, int] = defaultdict(int)

    def add(self, original: str, pii_type: str) -> str:
        """Map an original value to a placeholder. Reuses existing mapping for duplicates."""
        key = original.lower()
        if key in self._original_to_placeholder:
            return self._original_to_placeholder[key]

        self._counters[pii_type] += 1
        placeholder = self._format.format(
            type=pii_type, id=self._counters[pii_type]
        )

        self._original_to_placeholder[key] = placeholder
        self._placeholder_to_original[placeholder] = original
        return placeholder

    def restore(self, text: str) -> str:
        """Replace all placeholders in text with their original values."""
        result = text
        # Sort by length descending to avoid partial replacements
        for placeholder, original in sorted(
            self._placeholder_to_original.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            result = result.replace(placeholder, original)
        return result

    def get_original(self, placeholder: str) -> str | None:
        """Look up the original value for a placeholder."""
        return self._placeholder_to_original.get(placeholder)

    def get_placeholder(self, original: str) -> str | None:
        """Look up the placeholder for an original value."""
        return self._original_to_placeholder.get(original.lower())

    @property
    def entries(self) -> dict[str, str]:
        """Return placeholder -> original mapping."""
        return dict(self._placeholder_to_original)

    def to_dict(self) -> dict:
        """Serialize for storage/audit."""
        return {
            "format": self._format,
            "mappings": dict(self._placeholder_to_original),
            "counters": dict(self._counters),
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlaceholderMap:
        """Deserialize from stored format."""
        pm = cls(placeholder_format=data["format"])
        pm._counters = defaultdict(int, data["counters"])
        for placeholder, original in data["mappings"].items():
            pm._placeholder_to_original[placeholder] = original
            pm._original_to_placeholder[original.lower()] = placeholder
        return pm

    def __len__(self) -> int:
        return len(self._placeholder_to_original)

    def __repr__(self) -> str:
        return f"PlaceholderMap({len(self)} entries)"
