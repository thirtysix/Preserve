"""
False positive tests — text that should produce ZERO PII detections.

Validates precision: none of these should trigger the scrubber.
"""

import pytest

from preserve.config import PreserveConfig, SensitivityLevel
from preserve.scrubber import Scrubber


@pytest.fixture(scope="module")
def scrubber():
    return Scrubber(PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        use_name_scorer=True,
    ))


class TestNoFalsePositives:
    """Text that contains NO PII and should produce zero detections."""

    def test_clock_time_not_dob(self, scrubber):
        # A bare time must not be parsed as a date of birth.
        for text in ("meeting at 12:34:56 today", "backup ran 23:59:59", "standup at 09:30"):
            result = scrubber.scrub(text)
            assert not any(d.replacement_type == "DOB" for d in result.detections), \
                f"time -> DOB: {[d.matched_text for d in result.detections]}"

    def test_relative_and_duration_dates_not_dob(self, scrubber):
        # Relative/fuzzy date references and durations are not PII.
        for text in ("let's meet tomorrow", "as we discussed yesterday",
                     "the remaining 10% released one year after completion",
                     "a price deal for 1, 3, 5, 7 and 10 years"):
            result = scrubber.scrub(text)
            assert not any(d.replacement_type == "DOB" for d in result.detections), \
                f"relative date -> DOB: {[d.matched_text for d in result.detections]}"

    def test_policy_words_not_insurance_id(self, scrubber):
        # "policy"/"health insurance" + a plain word must not be an insurance ID;
        # a real ID has digits.
        for text in ("policy reform can revolutionize education",
                     "contact your health insurance provider",
                     "due to recent policy changes we updated terms"):
            result = scrubber.scrub(text)
            assert not any(d.replacement_type == "INSURANCE_ID" for d in result.detections), \
                f"policy word -> INSURANCE_ID: {[d.matched_text for d in result.detections]}"

    def test_bank_keyword_substring_not_financial(self, scrubber):
        # "account"/"bank" inside larger words must not trigger a FINANCIAL match,
        # and a non-numeric value after the keyword must not be captured.
        for text in ("registered public accountants filed the report",
                     "a trustee in bankruptcy was appointed",
                     "Thanks, the Account Team"):
            result = scrubber.scrub(text)
            assert not any(d.replacement_type == "FINANCIAL" for d in result.detections), \
                f"bank substring -> FINANCIAL: {[d.matched_text for d in result.detections]}"

    def test_mac_address_not_name(self, scrubber):
        # Hex groups separated by ':' must not be read as a name pair.
        result = scrubber.scrub("MAC aa:bb:cc:dd:ee:ff on the switch")
        assert not any(d.replacement_type == "NAME" for d in result.detections), \
            f"MAC -> NAME: {[d.matched_text for d in result.detections]}"

    def test_technical_prose(self, scrubber):
        text = "The algorithm processes data in parallel using 8 threads across the CPU cores."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_code_snippet(self, scrubber):
        text = "def calculate_total(items): return sum(item.price for item in items)"
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_medical_terminology(self, scrubber):
        text = "The patient presented with acute myocardial infarction. Treatment protocol includes aspirin 325mg and heparin drip."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_geographic_description(self, scrubber):
        text = "The conference will be held in Helsinki, Finland. Attendees from Europe and Asia are expected."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_product_description(self, scrubber):
        text = "The new Model X features a 12-inch display, 256GB storage, and runs on version 4.2 of the operating system."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_cooking_recipe(self, scrubber):
        text = "Preheat oven to 350 degrees. Mix 2 cups flour with 3 eggs. Bake for 25 minutes."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_sports_report(self, scrubber):
        text = "The team scored 3 goals in the second half. The final score was 4-1. The next match is on Saturday."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_weather_report(self, scrubber):
        text = "Tomorrow's forecast: partly cloudy with a high of 72 degrees. Wind from the northwest at 10 mph."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_business_jargon(self, scrubber):
        text = "We need to leverage our core competencies to drive synergies across the organization and maximize stakeholder value."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_instructions(self, scrubber):
        text = "Please summarize the following data and provide recommendations for improving detection rates across all categories."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_error_message(self, scrubber):
        text = "Error 404: Page not found. Please check the URL and try again. If the problem persists, contact support."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_git_log(self, scrubber):
        text = "commit abc123def: Fixed bug in parser module. Refactored the validation logic for better performance."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_math_expression(self, scrubber):
        text = "The formula is: y = mx + b, where m is the slope and b is the y-intercept. For x = 5, y = 17."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_legal_boilerplate(self, scrubber):
        text = "This agreement is governed by the laws of the jurisdiction in which the service is provided. All disputes shall be resolved through arbitration."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_release_notes(self, scrubber):
        text = "Version 2.3.1 release notes: Fixed memory leak in connection pool. Improved startup time by 40%. Added support for PostgreSQL 15."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"


class TestBorderlineSafe:
    """Text that LOOKS like it might contain PII but doesn't."""

    def test_common_word_names(self, scrubber):
        """Words that are also names but used as common words."""
        text = "The rose garden blooms in spring. Grace and patience are important virtues."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_number_that_looks_like_ssn(self, scrubber):
        """A number format that resembles SSN but is clearly not one."""
        text = "The reference code is formatted as XXX-XX-XXXX where X is a digit."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_fictional_example(self, scrubber):
        """Clearly labeled as an example/placeholder."""
        text = "For example, a test value of 000-00-0000 is used in development environments."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_country_names_not_person_names(self, scrubber):
        """Countries and cities that could be mistaken for person names."""
        text = "The study was conducted in Jordan, Georgia, and Chad. Data from India and China was also included."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_disease_names(self, scrubber):
        """Medical conditions that shouldn't be flagged."""
        text = "Common conditions include Type 2 diabetes, essential hypertension, and bipolar disorder. Blood type O+ is the most common."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"

    def test_medication_names(self, scrubber):
        """Drug names that shouldn't be flagged."""
        text = "Prescribed medications: Metformin 500mg, Lisinopril 10mg, Atorvastatin 20mg. Take with food."
        result = scrubber.scrub(text)
        assert result.pii_count == 0, f"False positives: {[d.matched_text for d in result.detections]}"
