"""C2: secrets / credential detection."""

import pytest

from preserve import Scrubber, PreserveConfig, SensitivityLevel


@pytest.fixture(scope="module")
def scrub():
    return Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.STANDARD)).scrub


def _has_secret(result):
    return any(d.replacement_type == "SECRET" for d in result.detections)


# Fixtures are assembled from parts so no contiguous secret-looking literal
# exists in this file (avoids tripping secret scanners); the regexes still see
# the full string at runtime.
PEM = ("-----BEGIN " + "PRIVATE KEY-----\n"
       "MIIBVgIBADANBgkqhkiG9w0BAQEFAASCAVAwggFMAgEAAoGBAKxfakefakefake\n"
       "-----END " + "PRIVATE KEY-----")

POSITIVES = [
    "key " + "AKIA" + "IOSFODNN7EXAMPLE" + " in config",
    "token " + "ghp_" + "16C7e42F292c6912E7710c838347Ae178B4aXXXX" + " more",
    "anthropic " + "sk-ant-" + "api03-abc123DEF456ghi789JKL012mno" + " here",
    "openai " + "sk-proj-" + "abcdefghijklmnop1234567890" + " here",
    "google " + "AIza" + "B" * 35 + " used",
    "slack " + "xoxb-" + "1234567890-abcdEFGH" + " here",
    "stripe " + "sk_" + "live_" + "abcdefghijklmnop12345678" + " charge",
    "jwt " + "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
    "db " + "postgresql://" + "app:s3cr3tpw@db.internal:5432/main",
    "config password = hunter2longenough123",
    "Authorization: Bearer abcd1234efgh5678ijkl",
    PEM,
]

NEGATIVES = [
    "Please summarize the quarterly report for the board.",
    "The secret ingredient is love and patience.",
    "We discussed password policies and token bucket rate limiting.",
]


@pytest.mark.parametrize("text", POSITIVES)
def test_secret_detected(scrub, text):
    assert _has_secret(scrub(text)), f"missed secret in {text[:40]!r}"


@pytest.mark.parametrize("text", NEGATIVES)
def test_no_false_secret(scrub, text):
    assert not _has_secret(scrub(text)), f"false secret in {text!r}"


def test_secret_value_only_for_assignment(scrub):
    # The keyword itself must not be redacted, only the value.
    r = scrub("password = hunter2longenough123")
    secrets = [d.matched_text for d in r.detections if d.replacement_type == "SECRET"]
    assert secrets == ["hunter2longenough123"]
