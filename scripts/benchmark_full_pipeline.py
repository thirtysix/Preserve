#!/usr/bin/env python3
"""
Benchmark the full 3-layer Preserve pipeline against the 100-row test dataset.

Compares detection rates across configurations:
  A) Layer 2 only (regex patterns) — baseline
  B) Layer 1+2 (normalcy scanner + regex)
  C) Layer 1+2+3 (normalcy + regex + local LLM)

Uses the same test_data.csv and narrative format as test_against_dataset.py.

Usage:
    python scripts/benchmark_full_pipeline.py
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve import Scrubber, PreserveConfig, SensitivityLevel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "tests" / "test_data.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "Qwen3.5-0.8B-Q4_K_M.gguf"

N_THREADS = 4  # Keep CPU usage moderate

# Columns containing PII that regex should catch
PII_COLUMNS = [
    "full_name", "date_of_birth", "email", "phone", "national_id",
    "passport_number", "bank_account", "credit_card", "ip_address",
    "address", "emergency_contact_name", "emergency_contact_phone",
]


def load_data() -> list[dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_narrative(row: dict) -> str:
    """Convert a data row into a realistic natural-language prompt."""
    return (
        f"Patient {row['full_name']}, born {row['date_of_birth']}, age {row['age']}, "
        f"residing at {row['address']}, {row['region']}, {row['country']}. "
        f"Contact: {row['email']}, phone {row['phone']}. "
        f"National ID: {row['national_id']}. Passport: {row['passport_number']}. "
        f"Bank account: {row['bank_account']}. Credit card: {row['credit_card']}. "
        f"IP address: {row['ip_address']}. Annual salary: {row['annual_salary']}. "
        f"Primary diagnosis: {row['diagnosis_primary']}. "
        f"Secondary diagnosis: {row['diagnosis_secondary']}. "
        f"Medication: {row['current_medication']}. Blood type: {row['blood_type']}. "
        f"Emergency contact: {row['emergency_contact_name']} ({row['emergency_contact_phone']})."
    )


def check_pii_detected(value: str, scrub_result) -> bool:
    """Check if a specific PII value was detected in the scrub result."""
    if not value or value == "None":
        return True  # Skip empty/none values
    return value not in scrub_result.sanitized_text


def run_column_benchmark(rows: list[dict], scrubber: Scrubber, label: str) -> dict:
    """Test per-column detection on isolated values."""
    stats = {col: {"total": 0, "detected": 0} for col in PII_COLUMNS}

    for row in rows:
        for col in PII_COLUMNS:
            value = row.get(col, "")
            if not value or value == "None":
                continue
            stats[col]["total"] += 1
            result = scrubber.scrub(value)
            if result.pii_found:
                stats[col]["detected"] += 1

    total_d = sum(s["detected"] for s in stats.values())
    total_t = sum(s["total"] for s in stats.values())
    return {"label": label, "column_stats": stats, "total_detected": total_d, "total_items": total_t}


def run_narrative_benchmark(rows: list[dict], scrubber: Scrubber, label: str) -> dict:
    """Test detection on full narrative text (realistic prompts)."""
    results = {
        "label": label,
        "rows_tested": 0,
        "total_pii_values": 0,
        "total_detected": 0,
        "per_column": {col: {"total": 0, "detected": 0} for col in PII_COLUMNS},
        "total_time_s": 0,
        "round_trips_ok": 0,
    }

    for i, row in enumerate(rows, 1):
        narrative = build_narrative(row)
        t0 = time.time()
        result = scrubber.scrub(narrative)
        elapsed = time.time() - t0
        results["total_time_s"] += elapsed
        results["rows_tested"] += 1

        # Check round-trip
        restored = scrubber.restore(result.sanitized_text, result.placeholder_map)
        if restored == narrative:
            results["round_trips_ok"] += 1

        # Check each PII column value
        row_detected = 0
        row_total = 0
        for col in PII_COLUMNS:
            value = row.get(col, "")
            if not value or value == "None":
                continue
            results["total_pii_values"] += 1
            results["per_column"][col]["total"] += 1
            row_total += 1
            if value not in result.sanitized_text:
                results["total_detected"] += 1
                results["per_column"][col]["detected"] += 1
                row_detected += 1

        # Progress output
        overall_rate = results["total_detected"] / results["total_pii_values"] * 100 if results["total_pii_values"] > 0 else 0
        layers = [d.detection_layer for d in result.detections]
        llm_count = layers.count("normalcy+llm")
        regex_count = len(layers) - llm_count
        print(
            f"  [{i:3d}/{len(rows)}] {row['country']:12s} | "
            f"{elapsed:5.1f}s | "
            f"{row_detected}/{row_total} detected | "
            f"regex={regex_count} llm={llm_count} | "
            f"running: {overall_rate:.1f}%",
            flush=True,
        )

    return results


def print_narrative_results(results: dict):
    """Print narrative benchmark results."""
    print(f"\n  {'Column':<28s} {'Detected':>10s} {'Total':>8s} {'Rate':>8s}")
    print(f"  {'-'*28} {'-'*10} {'-'*8} {'-'*8}")

    for col in PII_COLUMNS:
        s = results["per_column"][col]
        rate = s["detected"] / s["total"] * 100 if s["total"] > 0 else 0
        indicator = "  " if rate >= 90 else "! " if rate >= 50 else "!!"
        print(f"{indicator}{col:<28s} {s['detected']:>10d} {s['total']:>8d} {rate:>7.1f}%")

    overall = results["total_detected"] / results["total_pii_values"] * 100 if results["total_pii_values"] > 0 else 0
    avg_time = results["total_time_s"] / results["rows_tested"] if results["rows_tested"] > 0 else 0
    print()
    print(f"  OVERALL: {results['total_detected']}/{results['total_pii_values']} ({overall:.1f}%)")
    print(f"  Round-trips OK: {results['round_trips_ok']}/{results['rows_tested']}")
    print(f"  Total time: {results['total_time_s']:.1f}s ({avg_time:.2f}s/row)")


def main():
    rows = load_data()
    print(f"Loaded {len(rows)} rows from test_data.csv")
    print(f"LLM model: {MODEL_PATH.name} ({'exists' if MODEL_PATH.exists() else 'MISSING'})")
    print(f"CPU threads: {N_THREADS}")
    print()

    configs = [
        (
            "A: Layer 2 only (regex)",
            PreserveConfig(
                sensitivity_level=SensitivityLevel.AGGRESSIVE,
                use_normalcy_scanner=False,
                use_llm_review=False,
            ),
        ),
        (
            "B: Layer 1+2 (normalcy + regex)",
            PreserveConfig(
                sensitivity_level=SensitivityLevel.AGGRESSIVE,
                use_normalcy_scanner=True,
                use_llm_review=False,
            ),
        ),
    ]

    # Only add Layer 3 if model exists
    if MODEL_PATH.exists():
        configs.append((
            "C: Layer 1+2+3 (normalcy + regex + LLM 0.8B)",
            PreserveConfig(
                sensitivity_level=SensitivityLevel.AGGRESSIVE,
                use_normalcy_scanner=True,
                use_llm_review=True,
                llm_model_path=str(MODEL_PATH),
                llm_use_chat=True,
                llm_n_threads=N_THREADS,
                llm_threshold=0.5,
            ),
        ))
    else:
        print(f"WARNING: LLM model not found at {MODEL_PATH}, skipping Layer 3 benchmark")
        print()

    all_results = []

    for label, config in configs:
        print(f"{'='*70}")
        print(f"  {label}")
        print(f"{'='*70}")

        scrubber = Scrubber(config)

        # Run narrative benchmark (full sentences, realistic prompts)
        result = run_narrative_benchmark(rows, scrubber, label)
        all_results.append(result)
        print_narrative_results(result)
        print()

    # --- Summary comparison ---
    print(f"{'='*70}")
    print(f"  COMPARISON SUMMARY (narrative mode, 100 rows)")
    print(f"{'='*70}")
    print()
    print(f"  {'Configuration':<45s} {'Detected':>10s} {'Total':>8s} {'Rate':>8s} {'Time':>10s}")
    print(f"  {'-'*45} {'-'*10} {'-'*8} {'-'*8} {'-'*10}")

    for r in all_results:
        rate = r["total_detected"] / r["total_pii_values"] * 100 if r["total_pii_values"] > 0 else 0
        print(
            f"  {r['label']:<45s} "
            f"{r['total_detected']:>10d} "
            f"{r['total_pii_values']:>8d} "
            f"{rate:>7.1f}% "
            f"{r['total_time_s']:>8.1f}s"
        )

    print()

    # Per-column comparison
    print(f"  {'Column':<28s}", end="")
    for r in all_results:
        short = r["label"].split(":")[0].strip()
        print(f" {short:>10s}", end="")
    print()
    print(f"  {'-'*28}", end="")
    for _ in all_results:
        print(f" {'-'*10}", end="")
    print()

    for col in PII_COLUMNS:
        print(f"  {col:<28s}", end="")
        for r in all_results:
            s = r["per_column"][col]
            rate = s["detected"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f" {rate:>9.1f}%", end="")
        print()

    print()

    # Save results
    output_path = PROJECT_ROOT / "tests" / "full_pipeline_benchmark.json"
    save_data = []
    for r in all_results:
        save_data.append({
            "label": r["label"],
            "total_detected": r["total_detected"],
            "total_pii_values": r["total_pii_values"],
            "detection_rate": round(r["total_detected"] / r["total_pii_values"] * 100, 1) if r["total_pii_values"] > 0 else 0,
            "total_time_s": round(r["total_time_s"], 1),
            "avg_time_per_row_s": round(r["total_time_s"] / r["rows_tested"], 2) if r["rows_tested"] > 0 else 0,
            "round_trips_ok": r["round_trips_ok"],
            "per_column": {
                col: {
                    "detected": r["per_column"][col]["detected"],
                    "total": r["per_column"][col]["total"],
                    "rate": round(r["per_column"][col]["detected"] / r["per_column"][col]["total"] * 100, 1) if r["per_column"][col]["total"] > 0 else 0,
                }
                for col in PII_COLUMNS
            },
        })
    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
