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

    # Test at each sensitivity level
    for level in [SensitivityLevel.MINIMAL, SensitivityLevel.STANDARD, SensitivityLevel.AGGRESSIVE]:
        print(f"{'=' * 70}")
        print(f"  SENSITIVITY: {level.value.upper()}")
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

    # Also test full-row scrubbing (simulating a natural language prompt)
    print(f"{'=' * 70}")
    print(f"  FULL-ROW NARRATIVE TEST (AGGRESSIVE)")
    print(f"{'=' * 70}")
    print()

    config = PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        use_normalcy_scanner=True,
    )
    scrubber = Scrubber(config)

    sample_rows = [rows[0], rows[1], rows[10], rows[25], rows[50], rows[75], rows[99]]

    for row in sample_rows:
        narrative = (
            f"Patient {row['full_name']}, born {row['date_of_birth']}, "
            f"residing at {row['address']}, {row['region']}, {row['country']}. "
            f"Contact: {row['email']}, phone {row['phone']}. "
            f"National ID: {row['national_id']}. "
            f"Primary diagnosis: {row['diagnosis_primary']}. "
            f"Medication: {row['current_medication']}. "
            f"Emergency contact: {row['emergency_contact_name']} ({row['emergency_contact_phone']})."
        )

        result = scrubber.scrub(narrative)
        types_found = list(result.pii_summary.keys())

        print(f"  Row {row['id']} ({row['country']}):")
        print(f"    PII found: {result.pii_count} items — {', '.join(types_found)}")
        print(f"    Sanitized: {result.sanitized_text[:120]}...")
        print(f"    Round-trip: {scrubber.restore(result.sanitized_text, result.placeholder_map) == narrative}")
        print()


if __name__ == "__main__":
    main()
