"""
Layer 2b: Domain-specific parsers.

Uses specialized libraries for validated PII detection:
- phonenumbers: Google's libphonenumber for international phone validation
- email-validator: RFC-compliant email validation with unicode support
- dateparser: Multilingual date extraction from free text
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("preserve.domain_parsers")


@dataclass
class DomainMatch:
    """A PII match from a domain-specific parser."""

    start: int
    end: int
    matched_text: str
    pii_type: str
    confidence: float
    parser: str  # Which parser found it


class PhoneParser:
    """Detect and validate phone numbers using Google's phonenumbers library."""

    def __init__(self, default_region: str = "US") -> None:
        import phonenumbers
        self._pn = phonenumbers
        self._default_region = default_region

    def find(self, text: str) -> list[DomainMatch]:
        matches = []
        for match in self._pn.PhoneNumberMatcher(text, self._default_region):
            # Validate it's a possible number
            if self._pn.is_valid_number(match.number):
                confidence = 0.95
            elif self._pn.is_possible_number(match.number):
                confidence = 0.7
            else:
                continue  # Skip invalid numbers

            matches.append(
                DomainMatch(
                    start=match.start,
                    end=match.end,
                    matched_text=match.raw_string,
                    pii_type="PHONE",
                    confidence=confidence,
                    parser="phonenumbers",
                )
            )
        return matches


class EmailParser:
    """Validate email addresses using email-validator (handles unicode)."""

    def __init__(self) -> None:
        import re
        # Broad email regex that catches unicode local parts
        self._pattern = re.compile(
            r"[A-Za-z0-9\u00C0-\u024F._%+\-]+@[A-Za-z0-9\u00C0-\u024F.\-]+\.[A-Za-z]{2,}",
        )

    def find(self, text: str) -> list[DomainMatch]:
        from email_validator import validate_email, EmailNotValidError

        matches = []
        for m in self._pattern.finditer(text):
            email_str = m.group()
            try:
                validate_email(email_str, check_deliverability=False)
                confidence = 0.95
            except EmailNotValidError:
                # Still include it but with lower confidence —
                # could be a valid but unusual email format
                confidence = 0.5

            matches.append(
                DomainMatch(
                    start=m.start(),
                    end=m.end(),
                    matched_text=email_str,
                    pii_type="EMAIL",
                    confidence=confidence,
                    parser="email_validator",
                )
            )
        return matches


class DateParser:
    """Extract dates from text using dateparser's search_dates()."""

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = languages  # e.g., ["en", "fi", "de"]

    def find(self, text: str) -> list[DomainMatch]:
        import dateparser.search

        matches = []
        try:
            results = dateparser.search.search_dates(
                text,
                languages=self._languages,
                settings={
                    "STRICT_PARSING": True,
                    "REQUIRE_PARTS": ["year"],  # Avoid matching bare day/month
                },
            )
        except Exception:
            results = None

        if not results:
            return matches

        for date_string, parsed_date in results:
            # Skip very short matches (e.g., "31" matching as a date)
            if len(date_string.strip()) < 6:
                continue

            # Find the position in the original text
            idx = text.find(date_string)
            if idx < 0:
                continue

            # Skip if this looks like an age, year, version, or duration
            if date_string.strip().isdigit() and len(date_string.strip()) <= 4:
                continue

            # Skip durations ("25 minutes", "3 hours", "2 days")
            import re as _re
            if _re.search(r"\d+\s*(?:minutes?|hours?|days?|weeks?|months?|seconds?|yrs?|hrs?|mins?|secs?)\b", date_string, _re.I):
                continue

            # Skip runaway spans (a real date is short, not a paragraph).
            if len(date_string) > 45:
                continue
            # Require an explicit calendar date in the matched text. Without one it
            # is a relative/fuzzy reference ("tomorrow", "next week", "3 years",
            # "one year after") or a bare clock time, which dateparser resolves to a
            # full date internally but is not PII.
            has_date = (
                _re.search(r"\b(?:18|19|20)\d{2}\b", date_string)               # explicit year
                or _re.search(r"\d{1,2}[/-]\d{1,2}", date_string)                # numeric date
                or _re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                              date_string, _re.I)                                 # month name
            )
            if not has_date:
                continue

            matches.append(
                DomainMatch(
                    start=idx,
                    end=idx + len(date_string),
                    matched_text=date_string,
                    pii_type="DOB",
                    confidence=0.6,  # Dates need context to confirm as DOB
                    parser="dateparser",
                )
            )
        return matches


class DomainParserLayer:
    """Orchestrates all domain-specific parsers."""

    def __init__(
        self,
        phone_region: str = "US",
        date_languages: list[str] | None = None,
    ) -> None:
        self._parsers = [
            PhoneParser(default_region=phone_region),
            EmailParser(),
            DateParser(languages=date_languages),
        ]

    def detect(self, text: str) -> list[DomainMatch]:
        """Run all domain parsers and return combined matches."""
        all_matches: list[DomainMatch] = []
        for parser in self._parsers:
            try:
                all_matches.extend(parser.find(text))
            except Exception as e:
                logger.debug("Domain parser %s failed: %s", type(parser).__name__, e)
        return all_matches
