"""Tests for the scrubbing pipeline."""

import pytest

from preserve.config import PreserveConfig, SensitivityLevel
from preserve.scrubber import Scrubber

# Fixtures (scrubber, aggressive_scrubber) are defined in conftest.py as session-scoped.


class TestScrubbing:
    def test_basic_scrub(self, scrubber):
        result = scrubber.scrub("Email me at john@example.com")
        assert "john@example.com" not in result.sanitized_text
        assert "[EMAIL_1]" in result.sanitized_text
        assert result.pii_found is True

    def test_no_pii(self, scrubber):
        result = scrubber.scrub("The weather is nice today.")
        assert result.sanitized_text == "The weather is nice today."
        assert result.pii_found is False
        assert result.pii_count == 0

    def test_multiple_pii(self, scrubber):
        text = "Email: a@b.com, SSN: 123-45-6789, Phone: (555) 123-4567"
        result = scrubber.scrub(text)
        assert "a@b.com" not in result.sanitized_text
        assert "123-45-6789" not in result.sanitized_text
        assert "(555) 123-4567" not in result.sanitized_text
        assert result.pii_count >= 3

    def test_pii_summary(self, scrubber):
        text = "Email: a@b.com, SSN: 123-45-6789"
        result = scrubber.scrub(text)
        summary = result.pii_summary
        assert "EMAIL" in summary
        assert "SSN" in summary


class TestRoundTrip:
    def test_restore_matches_original(self, scrubber):
        original = "Contact john@example.com or call (555) 123-4567 about SSN 123-45-6789"
        result = scrubber.scrub(original)
        restored = Scrubber.restore(result.sanitized_text, result.placeholder_map)
        assert restored == original

    def test_restore_no_pii(self, scrubber):
        original = "No sensitive data here"
        result = scrubber.scrub(original)
        restored = Scrubber.restore(result.sanitized_text, result.placeholder_map)
        assert restored == original

    def test_restore_duplicate_values(self, scrubber):
        original = "Email john@example.com and also john@example.com"
        result = scrubber.scrub(original)
        # Same email should get same placeholder
        assert result.sanitized_text.count("[EMAIL_1]") == 2
        restored = Scrubber.restore(result.sanitized_text, result.placeholder_map)
        assert restored == original


class TestScrubMessages:
    def test_scrub_chat_messages(self, scrubber):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "My email is john@example.com"},
        ]
        sanitized, pm, detections = scrubber.scrub_messages(messages)
        assert "john@example.com" not in sanitized[1]["content"]
        assert "[EMAIL_1]" in sanitized[1]["content"]
        # System message should be untouched if no PII
        assert sanitized[0]["content"] == "You are a helpful assistant."

    def test_preserves_role(self, scrubber):
        messages = [{"role": "user", "content": "Email: a@b.com"}]
        sanitized, _, _ = scrubber.scrub_messages(messages)
        assert sanitized[0]["role"] == "user"

    def test_non_string_content(self, scrubber):
        messages = [{"role": "user", "content": None}]
        sanitized, _, _ = scrubber.scrub_messages(messages)
        assert sanitized[0]["content"] is None


class TestEdgeCases:
    def test_empty_string(self, scrubber):
        result = scrubber.scrub("")
        assert result.sanitized_text == ""
        assert result.pii_count == 0

    def test_unicode_text(self, scrubber):
        result = scrubber.scrub("Contactez-moi: utilisateur@exemple.fr")
        assert "utilisateur@exemple.fr" not in result.sanitized_text

    def test_all_pii(self, scrubber):
        result = scrubber.scrub("123-45-6789")
        assert result.sanitized_text == "[SSN_1]"

    def test_known_names_config(self):
        config = PreserveConfig(known_names=["Alice Johnson"])
        scrubber = Scrubber(config)
        result = scrubber.scrub("Alice Johnson sent an email")
        assert "Alice Johnson" not in result.sanitized_text
        assert "[NAME_1]" in result.sanitized_text
