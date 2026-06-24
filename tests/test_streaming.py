"""Unit tests for the placeholder-aware stream restorer."""

from preserve.api.streaming import PlaceholderStreamRestorer

_MAP = {"[NAME_1]": "Alice", "[EMAIL_1]": "jane@acme.com"}


def _restore(s):
    for k, v in _MAP.items():
        s = s.replace(k, v)
    return s


def test_whole_token_in_one_feed():
    r = PlaceholderStreamRestorer(_restore)
    assert r.feed("hi [NAME_1]!") == "hi Alice!"
    assert r.flush() == ""


def test_placeholder_split_across_feeds():
    r = PlaceholderStreamRestorer(_restore)
    out = r.feed("write to [EMA")      # holds back "[EMA"
    assert out == "write to " and "[EMA" not in out
    out += r.feed("IL_1] now")         # completes -> restores
    assert out == "write to jane@acme.com now"
    assert r.flush() == ""


def test_unfinished_placeholder_flushed_verbatim():
    r = PlaceholderStreamRestorer(_restore)
    assert r.feed("the end [NAM") == "the end "
    assert r.flush() == "[NAM"   # never completed -> emitted as-is


def test_literal_bracket_not_held():
    r = PlaceholderStreamRestorer(_restore)
    # "arr[0] ok" has no in-progress placeholder -> emitted whole
    assert r.feed("arr[0] ok") == "arr[0] ok"
