"""
Checksum validators for structured PII patterns.

Validates regex matches using mathematical check-digit algorithms
to eliminate false positives. A regex may match "123-45-6789" but
only validation can confirm it has a structurally valid format.
"""

from __future__ import annotations


def luhn_check(number: str) -> bool:
    """Validate a number using the Luhn algorithm (credit cards, IMEI, etc.)."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 2:
        return False
    # Double every second digit from the right
    for i in range(len(digits) - 2, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    return sum(digits) % 10 == 0


def iban_check(iban: str) -> bool:
    """Validate an IBAN using MOD-97 (ISO 7064)."""
    cleaned = iban.replace(" ", "").upper()
    if len(cleaned) < 5 or not cleaned[:2].isalpha() or not cleaned[2:4].isdigit():
        return False
    # Move first 4 chars to end, convert letters to numbers (A=10, B=11, ...)
    rearranged = cleaned[4:] + cleaned[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch) - ord('A') + 10)
        else:
            return False
    return int(numeric) % 97 == 1


def finland_hetu_check(hetu: str) -> bool:
    """Validate a Finnish HETU personal identity code (mod-31 check)."""
    cleaned = hetu.replace(" ", "")
    if len(cleaned) != 11:
        return False
    try:
        # Extract the 9-digit number (6 date digits + 3 individual digits)
        date_part = cleaned[:6]
        individual = cleaned[8:11]  # Skip the century marker at [7]
        check_char = cleaned[10]    # Actually position 10
        nine_digits = int(date_part + individual[:3])
    except (ValueError, IndexError):
        return False
    lookup = "0123456789ABCDEFHJKLMNPRSTUVWXY"
    # The check character is at position 10 (last char)
    check_char = cleaned[-1]
    try:
        nine_digits = int(cleaned[:6] + cleaned[8:11])
    except ValueError:
        return False
    expected = lookup[nine_digits % 31]
    return check_char == expected


def spain_dni_check(dni: str) -> bool:
    """Validate a Spanish DNI (8 digits + letter via mod-23)."""
    cleaned = dni.strip()
    if len(cleaned) != 9:
        return False
    try:
        number = int(cleaned[:8])
    except ValueError:
        return False
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"
    return cleaned[8].upper() == letters[number % 23]


def spain_nie_check(nie: str) -> bool:
    """Validate a Spanish NIE (X/Y/Z prefix + 7 digits + letter)."""
    cleaned = nie.strip().upper()
    if len(cleaned) != 9 or cleaned[0] not in "XYZ":
        return False
    prefix_map = {"X": "0", "Y": "1", "Z": "2"}
    try:
        number = int(prefix_map[cleaned[0]] + cleaned[1:8])
    except ValueError:
        return False
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"
    return cleaned[8] == letters[number % 23]


def brazil_cpf_check(cpf: str) -> bool:
    """Validate a Brazilian CPF (2 check digits)."""
    digits = [int(d) for d in cpf if d.isdigit()]
    if len(digits) != 11:
        return False
    # Reject all-same-digit (e.g., 111.111.111-11)
    if len(set(digits)) == 1:
        return False
    # First check digit
    total = sum(d * w for d, w in zip(digits[:9], range(10, 1, -1)))
    check1 = 0 if total % 11 < 2 else 11 - (total % 11)
    if digits[9] != check1:
        return False
    # Second check digit
    total = sum(d * w for d, w in zip(digits[:10], range(11, 1, -1)))
    check2 = 0 if total % 11 < 2 else 11 - (total % 11)
    return digits[10] == check2


def netherlands_bsn_check(bsn: str) -> bool:
    """Validate a Dutch BSN using the 11-proof test."""
    digits = [int(d) for d in bsn if d.isdigit()]
    if len(digits) == 8:
        digits = [0] + digits  # Pad to 9
    if len(digits) != 9:
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    total = sum(d * w for d, w in zip(digits, weights))
    return total % 11 == 0 and total != 0


def uk_nhs_check(nhs: str) -> bool:
    """Validate a UK NHS number (mod-11 check digit)."""
    digits = [int(d) for d in nhs if d.isdigit()]
    if len(digits) != 10:
        return False
    weights = list(range(10, 1, -1))
    total = sum(d * w for d, w in zip(digits[:9], weights))
    remainder = total % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return False  # Invalid number
    return digits[9] == check


def south_korea_rrn_check(rrn: str) -> bool:
    """Validate a South Korean RRN (mod check digit)."""
    digits = [int(d) for d in rrn if d.isdigit()]
    if len(digits) != 13:
        return False
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(d * w for d, w in zip(digits[:12], weights))
    check = (11 - total % 11) % 10
    return digits[12] == check


# Map pattern names to their validators
VALIDATORS: dict[str, callable] = {
    "credit_card": lambda text: luhn_check(text),
    "iban": lambda text: iban_check(text),
    "finland_hetu": lambda text: finland_hetu_check(text),
    "spain_dni": lambda text: spain_dni_check(text),
    "spain_nie": lambda text: spain_nie_check(text),
    "brazil_cpf": lambda text: brazil_cpf_check(text),
    "netherlands_bsn": lambda text: netherlands_bsn_check(text.split()[-1] if ":" in text else text),
    "uk_nhs": lambda text: uk_nhs_check(text.split()[-1] if ":" in text else text),
    "south_korea_rrn": lambda text: south_korea_rrn_check(text),
}
