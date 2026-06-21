"""
Context-aware confidence scoring.

Adjusts PII detection confidence based on surrounding text.
"SSN: 123-45-6789" is higher confidence than a bare "123-45-6789".
"""

from __future__ import annotations

import re

# Keywords that boost confidence when found near a PII match.
# Maps PII replacement type -> list of (regex, confidence_boost) pairs.
CONTEXT_BOOSTERS: dict[str, list[tuple[re.Pattern, float]]] = {
    "SSN": [
        (re.compile(r"\b(?:SSN|social\s*security|soc\s*sec)\b", re.I), 0.3),
    ],
    "EMAIL": [
        (re.compile(r"\b(?:email|e-mail|mail|contact)\b", re.I), 0.1),
    ],
    "PHONE": [
        (re.compile(r"\b(?:phone|tel|call|mobile|cell|fax|contact|reach)\b", re.I), 0.2),
    ],
    "NAME": [
        (re.compile(r"\b(?:patient|client|employee|name|contact|applicant|Mr|Mrs|Ms|Dr)\b", re.I), 0.2),
    ],
    "ADDRESS": [
        (re.compile(r"\b(?:address|lives?\s*at|residing|located|street|home)\b", re.I), 0.2),
    ],
    "DOB": [
        (re.compile(r"\b(?:DOB|born|birth|birthday|date\s*of\s*birth|age)\b", re.I), 0.3),
    ],
    "CREDIT_CARD": [
        (re.compile(r"\b(?:card|credit|visa|mastercard|amex|payment)\b", re.I), 0.2),
    ],
    "IBAN": [
        (re.compile(r"\b(?:IBAN|bank|account|transfer)\b", re.I), 0.2),
    ],
    "PASSPORT": [
        (re.compile(r"\b(?:passport|travel\s*document)\b", re.I), 0.3),
    ],
    "IP": [
        (re.compile(r"\b(?:IP|address|server|host|network)\b", re.I), 0.1),
    ],
    "FI_HETU": [
        (re.compile(r"\b(?:henkilötunnus|HETU|personal\s*(?:identity|ID)|sosiaaliturvatunnus)\b", re.I), 0.3),
    ],
    "MRN": [
        (re.compile(r"\b(?:MRN|medical\s*record|chart|patient\s*(?:ID|number))\b", re.I), 0.2),
    ],
    "INSURANCE_ID": [
        (re.compile(r"\b(?:insurance|policy|member|plan|group)\b", re.I), 0.2),
    ],
}

# Generic boosters that apply to any PII type
GENERIC_BOOSTERS: list[tuple[re.Pattern, float]] = [
    # Colon or "is" right before the match suggests a label
    (re.compile(r"(?::\s*|is\s+)$"), 0.15),
]

# Context that REDUCES confidence (the match might not be real PII)
CONTEXT_REDUCERS: list[tuple[re.Pattern, float]] = [
    # Code-like context
    (re.compile(r"\b(?:example|test|sample|dummy|fake|placeholder|mock|lorem)\b", re.I), -0.3),
    # Documentation context
    (re.compile(r"\b(?:format|pattern|regex|e\.g\.|for\s*instance|such\s*as)\b", re.I), -0.2),
    # Variable/code assignment
    (re.compile(r"[=:]\s*['\"]"), -0.2),
]

# How many characters of surrounding context to examine
CONTEXT_WINDOW = 80


def score_context(
    text: str,
    match_start: int,
    match_end: int,
    pii_type: str,
    base_confidence: float = 0.7,
) -> float:
    """Score a PII match based on surrounding context.

    Args:
        text: The full text containing the match.
        match_start: Start offset of the match.
        match_end: End offset of the match.
        pii_type: The PII replacement type (e.g., "SSN", "EMAIL").
        base_confidence: Starting confidence before context adjustments.

    Returns:
        Adjusted confidence score, clamped to [0.0, 1.0].
    """
    # Extract surrounding context
    ctx_start = max(0, match_start - CONTEXT_WINDOW)
    ctx_end = min(len(text), match_end + CONTEXT_WINDOW)
    before = text[ctx_start:match_start]
    after = text[match_end:ctx_end]
    context = before + after

    confidence = base_confidence

    # Apply type-specific boosters
    boosters = CONTEXT_BOOSTERS.get(pii_type, [])
    for pattern, boost in boosters:
        if pattern.search(context):
            confidence += boost
            break  # Only apply the first matching booster per type

    # Apply generic boosters (check text immediately before match)
    for pattern, boost in GENERIC_BOOSTERS:
        if pattern.search(before):
            confidence += boost
            break

    # Apply reducers
    for pattern, reduction in CONTEXT_REDUCERS:
        if pattern.search(context):
            confidence += reduction  # reduction is negative

    return max(0.0, min(1.0, confidence))
