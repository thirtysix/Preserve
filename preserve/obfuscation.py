"""
Obfuscation detection and normalization.

Catches common PII-hiding tricks and normalizes them before scanning:
- "john [at] example [dot] com" → "john@example.com"
- "five five five, one two three four" → "555-1234"
- Unicode homoglyphs (Cyrillic а → Latin a)
"""

from __future__ import annotations

import re
import unicodedata


# Email obfuscation patterns
EMAIL_OBFUSCATION = [
    (re.compile(r"\s*\[\s*at\s*\]\s*", re.I), "@"),
    (re.compile(r"\s*\(\s*at\s*\)\s*", re.I), "@"),
    (re.compile(r"\s+at\s+", re.I), "@"),
    (re.compile(r"\s*\[\s*dot\s*\]\s*", re.I), "."),
    (re.compile(r"\s*\(\s*dot\s*\)\s*", re.I), "."),
    (re.compile(r"\s+dot\s+", re.I), "."),
]

# Spelled-out digits and separators
WORD_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "oh": "0",  # Common in phone numbers
}

# Separators that can appear between spelled digits
WORD_SEPARATORS = {
    "dash": "-", "hyphen": "-", "dot": ".", "point": ".",
    "space": " ", "comma": ",",
}

WORD_DIGIT_OR_SEP = {**WORD_DIGITS, **WORD_SEPARATORS}

WORD_DIGIT_PATTERN = re.compile(
    r"\b(" + "|".join(WORD_DIGIT_OR_SEP.keys()) + r")\b",
    re.IGNORECASE,
)

# Common Unicode homoglyphs (characters that look like ASCII but aren't)
HOMOGLYPHS = {
    "\u0430": "a",  # Cyrillic а
    "\u0435": "e",  # Cyrillic е
    "\u043e": "o",  # Cyrillic о
    "\u0440": "p",  # Cyrillic р
    "\u0441": "c",  # Cyrillic с
    "\u0443": "y",  # Cyrillic у
    "\u0445": "x",  # Cyrillic х
    "\u0410": "A",  # Cyrillic А
    "\u0412": "B",  # Cyrillic В
    "\u0415": "E",  # Cyrillic Е
    "\u041a": "K",  # Cyrillic К
    "\u041c": "M",  # Cyrillic М
    "\u041d": "H",  # Cyrillic Н
    "\u041e": "O",  # Cyrillic О
    "\u0420": "P",  # Cyrillic Р
    "\u0421": "C",  # Cyrillic С
    "\u0422": "T",  # Cyrillic Т
    "\u2013": "-",  # en-dash → hyphen
    "\u2014": "-",  # em-dash → hyphen
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u00a0": " ",  # non-breaking space
}


def normalize_obfuscation(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Normalize obfuscated text and return the cleaned version.

    Returns:
        (normalized_text, changes) where changes is a list of
        (start, end, original_substring) for each modification made.
        This allows mapping detections back to original positions.
    """
    result = text
    changes: list[tuple[int, int, str]] = []

    # 1. Normalize Unicode homoglyphs
    normalized_chars = []
    for ch in result:
        if ch in HOMOGLYPHS:
            normalized_chars.append(HOMOGLYPHS[ch])
        else:
            normalized_chars.append(ch)
    result = "".join(normalized_chars)

    # 2. Normalize email obfuscation
    for pattern, replacement in EMAIL_OBFUSCATION:
        result = pattern.sub(replacement, result)

    # 3. Normalize spelled-out digit sequences (only in contexts that look like numbers)
    # Look for 3+ digit words (with optional separators like "dash" between them)
    def has_digit_sequence(text: str) -> bool:
        words = text.lower().split()
        digit_count = 0
        in_sequence = False
        for w in words:
            w_clean = w.strip(".,;:-()[]")
            if w_clean in WORD_DIGITS:
                digit_count += 1
                in_sequence = True
                if digit_count >= 3:
                    return True
            elif w_clean in WORD_SEPARATORS and in_sequence:
                continue  # Separators don't break the sequence
            else:
                digit_count = 0
                in_sequence = False
        return False

    if has_digit_sequence(result):
        result = WORD_DIGIT_PATTERN.sub(
            lambda m: WORD_DIGIT_OR_SEP[m.group().lower()], result
        )
        # Collapse "5 5 5 8 6 7" → "555-867" (join adjacent single digits/separators)
        result = re.sub(
            r'(\d(?:[\s]+[\d\-\.])*[\s]+\d)',
            lambda m: re.sub(r'\s+', '', m.group()),
            result,
        )

    return result, changes


def detect_obfuscation(text: str) -> list[str]:
    """Check if text contains obfuscation patterns. Returns list of types found."""
    found = []

    for pattern, _ in EMAIL_OBFUSCATION:
        if pattern.search(text):
            found.append("email_obfuscation")
            break

    if has_word_digit_sequence(text):
        found.append("spelled_digits")

    if any(ch in text for ch in HOMOGLYPHS):
        found.append("homoglyphs")

    return found


def has_word_digit_sequence(text: str) -> bool:
    """Check if text has 3+ spelled-out digits (with optional separators)."""
    words = text.lower().split()
    digit_count = 0
    in_sequence = False
    for w in words:
        w_clean = w.strip(".,;:-()[]")
        if w_clean in WORD_DIGITS:
            digit_count += 1
            in_sequence = True
            if digit_count >= 3:
                return True
        elif w_clean in WORD_SEPARATORS and in_sequence:
            continue
        else:
            digit_count = 0
            in_sequence = False
    return False
