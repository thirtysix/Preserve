#!/usr/bin/env python3
"""
Run Preserve's detection pipeline against the 100-row test dataset.
Measures detection rates per column and identifies gaps.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve import Scrubber, PreserveConfig, SensitivityLevel


# Columns that contain PII we should detect
PII_COLUMNS = [
    "full_name",
    "date_of_birth",
    "email",
    "phone",
    "national_id",
    "passport_number",
    "bank_account",
    "credit_card",
    "ip_address",
    "address",
    "emergency_contact_name",
    "emergency_contact_phone",
]

# Columns with sensitive categorical data (not pattern-matchable, but privacy-relevant)
SENSITIVE_COLUMNS = [
    "sex",
    "sexual_orientation",
    "ethnicity",
    "religion",
    "political_party",
    "diagnosis_primary",
    "diagnosis_secondary",
    "current_medication",
    "blood_type",
    "disability_status",
    "genetic_markers",
    "mental_health_status",
    "annual_salary",
]


def main():
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data.csv")

    with open(data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows, {len(rows[0])} columns")
    print()

    # --- Test 1: ISOLATED VALUES (worst case: each value scrubbed with NO context) ---
    # Context-dependent patterns (passport, address, names) deliberately require a
    # nearby keyword, so they score low here. This is a lower bound, not the headline
    # number — see the IN-CONTEXT test below for realistic prompt-style detection.
    print("ISOLATED-VALUE TEST — each field scrubbed alone, no surrounding context.")
    print("(Lower bound: contextual patterns can't fire without their keywords.)")
    print()
    for level in [SensitivityLevel.MINIMAL, SensitivityLevel.STANDARD, SensitivityLevel.AGGRESSIVE]:
        print(f"{'=' * 70}")
        print(f"  SENSITIVITY: {level.value.upper()} (isolated values)")
        print(f"{'=' * 70}")

        config = PreserveConfig(sensitivity_level=level)
        scrubber = Scrubber(config)

        column_stats: dict[str, dict] = {col: {"total": 0, "detected": 0, "missed": []} for col in PII_COLUMNS}

        for row in rows:
            for col in PII_COLUMNS:
                value = row.get(col, "")
                if not value or value == "None":
                    continue

                column_stats[col]["total"] += 1
                result = scrubber.scrub(value)

                if result.pii_found:
                    column_stats[col]["detected"] += 1
                else:
                    if len(column_stats[col]["missed"]) < 3:
                        column_stats[col]["missed"].append(
                            f"[{row['country']}] {value}"
                        )

        print()
        print(f"  {'Column':<28s} {'Detected':>10s} {'Total':>8s} {'Rate':>8s}")
        print(f"  {'-'*28} {'-'*10} {'-'*8} {'-'*8}")

        total_detected = 0
        total_items = 0

        for col in PII_COLUMNS:
            stats = column_stats[col]
            rate = stats["detected"] / stats["total"] * 100 if stats["total"] > 0 else 0
            total_detected += stats["detected"]
            total_items += stats["total"]

            indicator = "  " if rate >= 90 else "! " if rate >= 50 else "!!"
            print(f"{indicator}{col:<28s} {stats['detected']:>10d} {stats['total']:>8d} {rate:>7.1f}%")

            if stats["missed"] and rate < 100:
                for example in stats["missed"][:2]:
                    print(f"    missed: {example[:70]}")

        overall_rate = total_detected / total_items * 100 if total_items > 0 else 0
        print()
        print(f"  OVERALL: {total_detected}/{total_items} ({overall_rate:.1f}%)")
        print()

    # --- Test 2: IN-CONTEXT RECALL (realistic: all PII fields in a natural prompt) ---
    # This is the headline measurement reported in the README. Each row becomes a
    # natural-language narrative containing all 12 PII fields; a field counts as
    # detected if any detection span overlaps its position (the same overlap rule
    # used elsewhere). Run over ALL rows, not a sample.
    print(f"{'=' * 70}")
    print(f"  IN-CONTEXT RECALL (AGGRESSIVE) — all fields in a natural prompt")
    print(f"{'=' * 70}")
    print()

    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    ctx_stats = {col: {"total": 0, "detected": 0} for col in PII_COLUMNS}
    round_trips_ok = 0

    for row in rows:
        narrative = (
            f"Patient: {row['full_name']}, born {row['date_of_birth']}, residing at "
            f"{row['address']}, {row['region']}, {row['country']}. Email {row['email']}, "
            f"phone {row['phone']}. National ID: {row['national_id']}. "
            f"Passport: {row['passport_number']}. Bank IBAN {row['bank_account']}. "
            f"Card {row['credit_card']}. IP {row['ip_address']}. "
            f"Emergency contact: {row['emergency_contact_name']} ({row['emergency_contact_phone']})."
        )
        result = scrubber.scrub(narrative)
        spans = [(d.start, d.end) for d in result.detections]
        if scrubber.restore(result.sanitized_text, result.placeholder_map) == narrative:
            round_trips_ok += 1

        for col in PII_COLUMNS:
            value = row.get(col, "")
            if not value or value == "None":
                continue
            ctx_stats[col]["total"] += 1
            idx = narrative.find(value)
            if idx < 0:
                continue
            a, b = idx, idx + len(value)
            if any(s < b and e > a for s, e in spans):
                ctx_stats[col]["detected"] += 1

    print(f"  {'Column':<28s} {'Detected':>10s} {'Total':>8s} {'Rate':>8s}")
    print(f"  {'-'*28} {'-'*10} {'-'*8} {'-'*8}")
    td = tt = 0
    for col in PII_COLUMNS:
        d, t = ctx_stats[col]["detected"], ctx_stats[col]["total"]
        td += d
        tt += t
        rate = d / t * 100 if t else 0
        indicator = "  " if rate >= 90 else "! " if rate >= 50 else "!!"
        print(f"{indicator}{col:<28s} {d:>10d} {t:>8d} {rate:>7.1f}%")
    print()
    print(f"  OVERALL (in context): {td}/{tt} ({td/tt*100:.1f}%)")
    print(f"  Reversible round-trip: {round_trips_ok}/{len(rows)} rows exact")


if __name__ == "__main__":
    main()
