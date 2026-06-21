"""
Allow-lists for known false positives.

Provides built-in exclusions for test data, placeholder values,
and common non-PII strings that match PII patterns. Users can
add their own exclusions via configuration.
"""

from __future__ import annotations

import re


# US fictional/test phone numbers (555-01xx range is reserved)
TEST_PHONES = re.compile(r"555[.\-\s]?01\d{2}")

# Clearly fake placeholder names (not real-sounding names)
PLACEHOLDER_NAMES = {
    "foo bar", "test user", "example user",
    "fulano de tal", "fulana de tal",  # Spanish/Portuguese placeholder
}

# Clearly non-deliverable domains
EXAMPLE_DOMAINS = {
    "localhost",
    "invalid",
}

# Common non-PII strings that match PII regex patterns
FALSE_POSITIVE_STRINGS = {
    "0.0.0.0",        # Not a real IP
    "255.255.255.255", # Broadcast
    "000-00-0000",     # Invalid SSN
    "000.000.000-00",  # Invalid CPF
    "0000000000",      # All zeros
}


class AllowList:
    """Filters out known false positives from PII detections."""

    def __init__(self, custom_allowed: list[str] | None = None) -> None:
        self._custom = set()
        if custom_allowed:
            self._custom = {s.lower().strip() for s in custom_allowed}

    def is_allowed(self, matched_text: str, pii_type: str) -> bool:
        """Return True if this match should be EXCLUDED (it's a known false positive)."""
        text_lower = matched_text.lower().strip()

        # User-configured allow-list
        if text_lower in self._custom:
            return True

        # Global false positives
        if matched_text.strip() in FALSE_POSITIVE_STRINGS:
            return True

        # Type-specific checks
        if pii_type == "PHONE":
            if TEST_PHONES.search(matched_text):
                return True

        if pii_type == "NAME":
            if text_lower in PLACEHOLDER_NAMES:
                return True

        if pii_type == "EMAIL":
            # Check if domain is an example/test domain
            if "@" in matched_text:
                domain = matched_text.split("@")[-1].lower().strip()
                if domain in EXAMPLE_DOMAINS:
                    return True

        if pii_type == "IP":
            # Allow private/reserved ranges if configured
            if matched_text.startswith(("127.", "0.", "255.")):
                return True

        return False
