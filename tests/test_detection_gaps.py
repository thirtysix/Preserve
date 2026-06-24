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


@pytest.mark.parametrize("text,expected", [
    ("by letter of 14 June 1994 the police", "14 June 1994"),
    ("born February 4, 1909 in Oslo", "February 4, 1909"),
    ("the deadline is June 2020", "June 2020"),
])
def test_month_name_dates(scrub, text, expected):
    dates = _types(scrub(text), "DATE")
    assert any(expected in d for d in dates), f"missed month-date in {text!r}: {dates}"


@pytest.mark.parametrize("text,expected", [
    ("DOB: 15.3.1990", "15.3.1990"),
    ("born 15.3.1990 in Helsinki", "15.3.1990"),
    ("the incident on 1.12.2020 was logged", "1.12.2020"),
])
def test_dot_separated_dates(scrub, text, expected):
    dates = _types(scrub(text), "DOB") + _types(scrub(text), "DATE")
    assert any(expected in d for d in dates), f"missed dot date in {text!r}: {dates}"


def test_version_and_ip_not_dates(scrub):
    # No 4-digit year -> not a date; IPs stay IPs.
    for text in ("upgraded to version 1.2.3 today", "server at 192.168.1.1 responded"):
        assert not any(d.replacement_type in ("DOB", "DATE") for d in scrub(text).detections), \
            f"version/IP -> date in {text!r}"


def test_month_name_date_requires_year(scrub):
    # No year -> not flagged (avoids "in June", "next September").
    assert _types(scrub("let's meet in June next year"), "DATE") == []


def test_secondary_address_units(scrub):
    for text, exp in [("accommodations at Apt. 259 starting", "Apt. 259"),
                      ("event held at Suite 786", "Suite 786"),
                      ("move to Unit 4B", "Unit 4B")]:
        addrs = _types(scrub(text), "ADDRESS")
        assert any(exp in a for a in addrs), f"missed {exp!r}: {addrs}"


def test_address_alphanumeric_house_number(scrub):
    addrs = _types(scrub("lives at 221B Baker Street, London"), "ADDRESS")
    assert any("221B Baker Street" in a for a in addrs), addrs
