"""Tests for PII detection engine."""

import pytest

from preserve.config import PreserveConfig, SensitivityLevel
from preserve.detectors import PIIDetector, PIIMatch

# Fixtures (detector_minimal, detector_standard, detector_aggressive)
# are defined in conftest.py as session-scoped to avoid reloading datasets.


class TestEmailDetection:
    def test_simple_email(self, detector_minimal):
        matches = detector_minimal.detect("Contact me at john@example.com please")
        assert len(matches) == 1
        assert matches[0].matched_text == "john@example.com"
        assert matches[0].replacement_type == "EMAIL"

    def test_complex_email(self, detector_minimal):
        matches = detector_minimal.detect("Email: first.last+tag@sub.domain.co.uk")
        assert len(matches) == 1
        assert "first.last+tag@sub.domain.co.uk" in matches[0].matched_text

    def test_no_email(self, detector_minimal):
        matches = detector_minimal.detect("This text has no email addresses")
        assert len(matches) == 0


class TestSSNDetection:
    def test_valid_ssn(self, detector_minimal):
        matches = detector_minimal.detect("My SSN is 123-45-6789")
        assert len(matches) == 1
        assert matches[0].matched_text == "123-45-6789"
        assert matches[0].replacement_type == "SSN"

    def test_not_ssn(self, detector_minimal):
        matches = detector_minimal.detect("Phone: 123-456-7890")
        # Should not match as SSN (wrong format)
        ssn_matches = [m for m in matches if m.replacement_type == "SSN"]
        assert len(ssn_matches) == 0


class TestLayer3Gate:
    """The smart gate that decides whether Layer 3 LLM review is worth running."""

    @staticmethod
    def _match(start, end, confidence):
        return PIIMatch(
            start=start,
            end=end,
            matched_text="x" * (end - start),
            pattern_name="test",
            replacement_type="TEST",
            sensitivity=SensitivityLevel.STANDARD,
            confidence=confidence,
        )

    def test_no_uncovered_spans_skips(self, detector_standard):
        assert not detector_standard._should_run_llm_review("abc", [(0, 3)], [], [])

    def test_substantial_uncovered_span_runs(self, detector_standard):
        # 7 alphanumeric chars, nothing from Layer 2 -> review.
        text = "Acme Corp months later"
        assert detector_standard._should_run_llm_review(text, [(0, 9)], [(0, 9)], [])

    def test_scattered_whitespace_punct_does_not_run(self, detector_standard):
        # Old gate summed raw chars and would fire; alnum-per-span gate must not.
        text = ".  -  ,  ?"
        assert not detector_standard._should_run_llm_review(
            text, [(0, len(text))], [(0, len(text))], []
        )

    def test_many_tiny_fragments_do_not_run(self, detector_standard):
        # Three 2-char fragments sum to 6 (> old threshold of 5) but none is
        # individually substantial, so the per-span gate skips review.
        text = "ab cd ef"
        uncovered = [(0, 2), (3, 5), (6, 8)]
        assert not detector_standard._should_run_llm_review(
            text, [(0, len(text))], uncovered, []
        )

    def test_skips_when_layer2_high_confidence_and_well_covered(self, detector_standard):
        # 30-char suspicious region; 4 alnum chars uncovered, Layer 2 covers the
        # rest (87%) at high confidence -> skip. The content gate passes first, so
        # this isolates the confidence gate (lower min_chars so 4 alnum clears it).
        text = "a" * 26 + "abcd"  # len 30; text[26:30] = "abcd"
        suspicious = [(0, 30)]
        uncovered = [(26, 30)]  # coverage = 26/30 = 0.87
        covering = [self._match(0, 26, 0.97)]
        detector_standard.config.llm_min_uncovered_chars = 3
        try:
            assert not detector_standard._should_run_llm_review(
                text, suspicious, uncovered, covering
            )
        finally:
            detector_standard.config.llm_min_uncovered_chars = 5

    def test_runs_when_layer2_low_confidence(self, detector_standard):
        # Same high coverage (80%), but Layer 2 is unsure -> let the LLM look.
        text = "Smithx" + "y" * 24  # len 30; text[0:6] = "Smithx" (6 alnum)
        suspicious = [(0, 30)]
        uncovered = [(0, 6)]  # coverage = 24/30 = 0.80
        low_conf = [self._match(6, 30, 0.4)]
        assert detector_standard._should_run_llm_review(
            text, suspicious, uncovered, low_conf
        )


class TestPhoneDetection:
    def test_parenthesized(self, detector_standard):
        matches = detector_standard.detect("Call (555) 123-4567")
        phone_matches = [m for m in matches if m.replacement_type == "PHONE"]
        assert len(phone_matches) == 1

    def test_dashed(self, detector_standard):
        matches = detector_standard.detect("Call 555-123-4567")
        phone_matches = [m for m in matches if m.replacement_type == "PHONE"]
        assert len(phone_matches) == 1

    def test_not_at_minimal(self, detector_minimal):
        matches = detector_minimal.detect("Call (555) 123-4567")
        phone_matches = [m for m in matches if m.replacement_type == "PHONE"]
        assert len(phone_matches) == 0


class TestIPDetection:
    def test_valid_ip(self, detector_standard):
        matches = detector_standard.detect("Server at 192.168.1.1 is down")
        ip_matches = [m for m in matches if m.replacement_type == "IP"]
        assert len(ip_matches) == 1
        assert ip_matches[0].matched_text == "192.168.1.1"

    def test_invalid_ip(self, detector_standard):
        matches = detector_standard.detect("Value 999.999.999.999 is invalid")
        ip_matches = [m for m in matches if m.replacement_type == "IP"]
        assert len(ip_matches) == 0


class TestNameDetection:
    def test_with_title(self, detector_aggressive):
        matches = detector_aggressive.detect("Dr. Sarah Chen was present")
        name_matches = [m for m in matches if m.replacement_type == "NAME"]
        assert len(name_matches) == 1

    def test_without_title(self, detector_aggressive):
        # Without title, regex heuristic won't catch it
        matches = detector_aggressive.detect("Sarah Chen was present")
        name_matches = [m for m in matches if m.replacement_type == "NAME"]
        assert len(name_matches) == 0

    def test_known_names(self):
        config = PreserveConfig(known_names=["John Doe", "Jane Smith"])
        detector = PIIDetector(config)
        matches = detector.detect("John Doe met Jane Smith at the cafe")
        name_matches = [m for m in matches if m.replacement_type == "NAME"]
        assert len(name_matches) == 2


class TestDOBDetection:
    def test_with_context(self, detector_standard):
        matches = detector_standard.detect("DOB 03/15/1985")
        dob_matches = [m for m in matches if m.replacement_type == "DOB"]
        assert len(dob_matches) == 1

    def test_date_of_birth_prefix(self, detector_standard):
        matches = detector_standard.detect("date of birth: 12/25/1990")
        dob_matches = [m for m in matches if m.replacement_type == "DOB"]
        assert len(dob_matches) == 1


class TestSensitivityLevels:
    def test_minimal_only_high_confidence(self, detector_minimal):
        text = "Email: a@b.com, SSN: 123-45-6789, Phone: (555) 123-4567, IP: 10.0.0.1"
        matches = detector_minimal.detect(text)
        types = {m.replacement_type for m in matches}
        assert "EMAIL" in types
        assert "SSN" in types
        assert "PHONE" not in types
        assert "IP" not in types

    def test_standard_adds_phone_ip(self, detector_standard):
        text = "Phone: (555) 123-4567, IP: 10.0.0.1"
        matches = detector_standard.detect(text)
        types = {m.replacement_type for m in matches}
        assert "PHONE" in types
        assert "IP" in types

    def test_aggressive_adds_names_addresses(self, detector_aggressive):
        text = "Dr. Smith lives at 123 Main Street"
        matches = detector_aggressive.detect(text)
        types = {m.replacement_type for m in matches}
        assert "NAME" in types or "ADDRESS" in types


class TestDeduplication:
    def test_no_duplicate_spans(self, detector_standard):
        text = "Contact john@example.com or call (555) 123-4567"
        matches = detector_standard.detect(text)
        # Check no two matches overlap
        for i, m1 in enumerate(matches):
            for m2 in matches[i + 1 :]:
                assert m1.end <= m2.start or m2.end <= m1.start


class TestMultiplePII:
    def test_multiple_same_type(self, detector_minimal):
        text = "Email a@b.com and c@d.com"
        matches = detector_minimal.detect(text)
        email_matches = [m for m in matches if m.replacement_type == "EMAIL"]
        assert len(email_matches) == 2

    def test_no_pii(self, detector_aggressive):
        text = "The weather is nice today."
        matches = detector_aggressive.detect(text)
        assert len(matches) == 0
