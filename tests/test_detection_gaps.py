"""Regression tests for the C1 detection-gap fixes: IPv6 and alphanumeric
house numbers."""

import pytest

from preserve import Scrubber, PreserveConfig, SensitivityLevel


@pytest.fixture(scope="module")
def scrub():
    return Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE)).scrub


def _types(result, t):
    return [d.matched_text for d in result.detections if d.replacement_type == t]


@pytest.mark.parametrize("text,expected", [
    ("host 2001:0db8:85a3:0000:0000:8a2e:0370:7334 up", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"),
    ("compressed 2001:db8::1 ok", "2001:db8::1"),
    ("loopback ::1 here", "::1"),
    ("link fe80::1ff:fe23:4567:890a%eth0 up", "fe80::1ff:fe23:4567:890a%eth0"),
])
def test_ipv6_detected(scrub, text, expected):
    ips = _types(scrub(text), "IP")
    assert any(expected in m or m in expected for m in ips), f"missed IPv6 in {text!r}: {ips}"


@pytest.mark.parametrize("text", [
    "MAC aa:bb:cc:dd:ee:ff device",   # 6 hextets, no '::' -> not IPv6
    "ratio 3:4 and 5:6 today",
])
def test_ipv6_no_false_positive(scrub, text):
    assert _types(scrub(text), "IP") == [], f"false IPv6 in {text!r}"


def test_address_alphanumeric_house_number(scrub):
    addrs = _types(scrub("lives at 221B Baker Street, London"), "ADDRESS")
    assert any("221B Baker Street" in a for a in addrs), addrs
