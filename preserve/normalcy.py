"""
Layer 1: Normalcy scanner.

Scores text regions by how "normal" (non-personal) they appear.
Regions with low normalcy scores get extra scrutiny from Layer 2 (pattern matching)
and Layer 3 (local LLM review).

The approach inverts typical PII detection: instead of only finding PII we know about,
we flag anything that doesn't look like safe, generic text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TextRegion:
    """A scored region of text."""

    start: int
    end: int
    text: str
    normalcy_score: float  # 0.0 = highly suspicious, 1.0 = clearly safe
    safe_labels: list[str] = field(default_factory=list)  # Which safe patterns matched


@dataclass
class SafePattern:
    """A pattern that identifies normal, non-personal text."""

    name: str
    regex: re.Pattern
    weight: float  # How much this contributes to normalcy (0.0-1.0)


# --- Built-in safe text patterns ---
# These match text that is clearly NOT personal information.

BUILTIN_SAFE_PATTERNS: list[SafePattern] = [
    # Code and technical content
    SafePattern(
        name="code_block",
        regex=re.compile(
            r"(?:def |class |import |from |return |if |for |while |try:|except:|"
            r"function |const |let |var |=>|->|\{\{|\}\}|"
            r"SELECT |INSERT |UPDATE |DELETE |CREATE |DROP )",
            re.IGNORECASE,
        ),
        weight=0.9,
    ),
    SafePattern(
        name="url",
        regex=re.compile(r"https?://\S+"),
        weight=0.8,
    ),
    SafePattern(
        name="file_path",
        regex=re.compile(r"(?:/[\w.-]+){2,}|(?:[A-Z]:\\[\w\\.-]+)"),
        weight=0.8,
    ),
    SafePattern(
        name="json_xml",
        regex=re.compile(r'[{}\[\]":].*[{}\[\]":]|<\/?[a-zA-Z][^>]*>'),
        weight=0.7,
    ),

    # Common instruction language
    SafePattern(
        name="instruction_phrases",
        regex=re.compile(
            r"\b(?:please|summarize|explain|describe|list|compare|analyze|translate|"
            r"write|create|generate|help me|how to|what is|can you|could you|"
            r"I need|we need|the following|for example|in order to|make sure|"
            r"step \d|note that|keep in mind|as follows)\b",
            re.IGNORECASE,
        ),
        weight=0.6,
    ),

    # Boilerplate / generic language
    SafePattern(
        name="generic_connectors",
        regex=re.compile(
            r"\b(?:the|a|an|is|are|was|were|been|being|have|has|had|do|does|did|"
            r"will|would|shall|should|can|could|may|might|must|need|"
            r"and|but|or|nor|for|yet|so|if|then|else|when|while|"
            r"this|that|these|those|it|they|we|you|he|she|"
            r"with|from|into|about|between|through|during|before|after|"
            r"however|therefore|furthermore|moreover|although|because|since|"
            r"according to|in addition|on the other hand|as a result)\b",
            re.IGNORECASE,
        ),
        weight=0.3,
    ),

    # Technical/scientific terms
    SafePattern(
        name="technical_terms",
        regex=re.compile(
            r"\b(?:algorithm|database|server|client|API|endpoint|protocol|"
            r"configuration|implementation|deployment|architecture|framework|"
            r"function|method|variable|parameter|module|package|library|"
            r"analysis|hypothesis|experiment|result|conclusion|methodology|"
            r"percentage|coefficient|standard deviation|mean|median|"
            r"diagnosis|treatment|symptom|condition|medication|procedure)\b",
            re.IGNORECASE,
        ),
        weight=0.5,
    ),

    # Numbers in safe contexts
    SafePattern(
        name="safe_numbers",
        regex=re.compile(
            r"(?:version|v|step|chapter|section|page|item|row|column|line|"
            r"figure|table|example|option|level|tier|grade|score|count|"
            r"port|error|code|status|id)\s*(?:#|:)?\s*\d+",
            re.IGNORECASE,
        ),
        weight=0.7,
    ),

    # Units and measurements
    SafePattern(
        name="measurements",
        regex=re.compile(
            r"\d+(?:\.\d+)?\s*(?:kg|lb|mg|g|oz|km|mi|m|cm|mm|ft|in|"
            r"°[CF]|mph|kph|ms|sec|min|hr|GB|MB|KB|TB|px|em|rem|%)\b",
            re.IGNORECASE,
        ),
        weight=0.8,
    ),

    # Dates in safe editorial context (not DOB-like)
    SafePattern(
        name="editorial_date",
        regex=re.compile(
            r"(?:published|updated|created|modified|posted|released|"
            r"as of|since|until|by|deadline|due|effective)\s+"
            r"(?:on\s+)?\w+\s+\d{1,2},?\s+\d{4}",
            re.IGNORECASE,
        ),
        weight=0.7,
    ),
]


class NormalcyScanner:
    """Scores text regions by how 'normal' (non-personal) they appear."""

    def __init__(
        self,
        custom_safe_patterns: list[dict] | None = None,
        window_size: int = 80,
        stride: int = 40,
    ) -> None:
        self._safe_patterns = list(BUILTIN_SAFE_PATTERNS)
        self._window_size = window_size
        self._stride = stride

        # Add user-supplied domain-specific safe patterns
        if custom_safe_patterns:
            for cp in custom_safe_patterns:
                self._safe_patterns.append(
                    SafePattern(
                        name=cp["name"],
                        regex=re.compile(cp["regex"], re.IGNORECASE),
                        weight=cp.get("weight", 0.6),
                    )
                )

    def scan(self, text: str) -> list[TextRegion]:
        """Score all regions of text. Returns regions sorted by normalcy score (lowest first)."""
        if not text:
            return []

        regions: list[TextRegion] = []

        # Slide a window across the text
        for start in range(0, len(text), self._stride):
            end = min(start + self._window_size, len(text))
            chunk = text[start:end]

            if not chunk.strip():
                regions.append(TextRegion(start, end, chunk, 1.0, ["whitespace"]))
                continue

            score, labels = self._score_region(chunk)
            regions.append(TextRegion(start, end, chunk, score, labels))

        return sorted(regions, key=lambda r: r.normalcy_score)

    def get_suspicious_regions(
        self, text: str, threshold: float = 0.5
    ) -> list[TextRegion]:
        """Return only regions scoring below the threshold."""
        return [r for r in self.scan(text) if r.normalcy_score < threshold]

    def get_suspicious_spans(
        self, text: str, threshold: float = 0.5
    ) -> list[tuple[int, int]]:
        """Return merged character spans of suspicious regions."""
        regions = self.get_suspicious_regions(text, threshold)
        if not regions:
            return []

        # Merge overlapping spans
        spans = sorted((r.start, r.end) for r in regions)
        merged: list[tuple[int, int]] = [spans[0]]
        for start, end in spans[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def _score_region(self, chunk: str) -> tuple[float, list[str]]:
        """Score a text chunk. Higher = more normal/safe."""
        matched_weights: list[float] = []
        labels: list[str] = []

        for pattern in self._safe_patterns:
            if pattern.regex.search(chunk):
                matched_weights.append(pattern.weight)
                labels.append(pattern.name)

        if not matched_weights:
            # No safe patterns matched — this is suspicious
            # But apply heuristics: short chunks, pure punctuation, etc. are fine
            if len(chunk.strip()) < 5:
                return 0.8, ["short"]
            if not any(c.isalnum() for c in chunk):
                return 0.9, ["non_alnum"]
            return 0.0, []

        # Combine weights: diminishing returns for multiple matches
        # First match contributes fully, subsequent ones contribute less
        sorted_weights = sorted(matched_weights, reverse=True)
        score = 0.0
        remaining = 1.0
        for w in sorted_weights:
            contribution = w * remaining * 0.7
            score += contribution
            remaining -= contribution

        return min(score, 1.0), labels
