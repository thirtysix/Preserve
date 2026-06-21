#!/usr/bin/env python3
"""
Benchmark local LLM models for PII detection.

Tests Qwen3.5 0.8B, 2B, and 4B (Q4_K_M) against a set of text samples
containing known PII. Measures accuracy, speed, and JSON reliability.

Usage:
    python scripts/benchmark_llm.py
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve.llm_review import LLMReviewer, build_prompt

# --- Test cases: text with known PII ---
# Each case has input text and expected detections (type, substring)

TEST_CASES = [
    {
        "id": "bare_names_western",
        "text": "Aurora Rossi called about her appointment. Ava Tremblay confirmed attendance.",
        "expected": [
            ("NAME", "Aurora Rossi"),
            ("NAME", "Ava Tremblay"),
        ],
    },
    {
        "id": "bare_names_nordic",
        "text": "Pekka Korhonen and Sari Laine submitted their applications yesterday.",
        "expected": [
            ("NAME", "Pekka Korhonen"),
            ("NAME", "Sari Laine"),
        ],
    },
    {
        "id": "bare_names_asian",
        "text": "Min-jun Kim was referred by Haruto Sato for the consultation.",
        "expected": [
            ("NAME", "Min-jun Kim"),
            ("NAME", "Haruto Sato"),
        ],
    },
    {
        "id": "bare_names_latin",
        "text": "Sofía García and Santiago Hernández filed the paperwork on Monday.",
        "expected": [
            ("NAME", "Sofía García"),
            ("NAME", "Santiago Hernández"),
        ],
    },
    {
        "id": "intl_address_italian",
        "text": "She lives at Via Roma 31, Emilia-Romagna, Italy.",
        "expected": [
            ("ADDRESS", "Via Roma 31"),
        ],
    },
    {
        "id": "intl_address_finnish",
        "text": "His office is at Mannerheimintie 42, Helsinki.",
        "expected": [
            ("ADDRESS", "Mannerheimintie 42"),
        ],
    },
    {
        "id": "intl_address_mexican",
        "text": "The clinic is located at Calle Reforma 156, Mexico City.",
        "expected": [
            ("ADDRESS", "Calle Reforma 156"),
        ],
    },
    {
        "id": "intl_address_german",
        "text": "Please send documents to Hauptstraße 88, Munich.",
        "expected": [
            ("ADDRESS", "Hauptstraße 88"),
        ],
    },
    {
        "id": "standalone_dates",
        "text": "Born 1971-04-05, admitted 15/03/1985, discharged 2025-01-20.",
        "expected": [
            ("DOB", "1971-04-05"),
            ("DOB", "15/03/1985"),
            ("DOB", "2025-01-20"),
        ],
    },
    {
        "id": "passport_numbers",
        "text": "Passport CC6770619 was issued in Rome. UK passport 567890123.",
        "expected": [
            ("PASSPORT", "CC6770619"),
            ("PASSPORT", "567890123"),
        ],
    },
    {
        "id": "mixed_pii",
        "text": (
            "Patient Mikko Virtanen, born 1985-03-15, residing at "
            "Fredrikinkatu 22, Helsinki. Passport XP4567890. "
            "Emergency contact: Aino Korhonen (+358 44 1234567)."
        ),
        "expected": [
            ("NAME", "Mikko Virtanen"),
            ("DOB", "1985-03-15"),
            ("ADDRESS", "Fredrikinkatu 22"),
            ("PASSPORT", "XP4567890"),
            ("NAME", "Aino Korhonen"),
            ("PHONE", "+358 44 1234567"),
        ],
    },
    {
        "id": "no_pii_medical",
        "text": "The treatment protocol follows standard guidelines for acute myocardial infarction. Prescribe Metformin 500mg.",
        "expected": [],
    },
    {
        "id": "no_pii_instructions",
        "text": "Please summarize the data and generate a report with recommendations for improving outcomes across all departments.",
        "expected": [],
    },
    {
        "id": "no_pii_technical",
        "text": "Deploy version 4.2 to the staging server at port 8080. Run the integration tests before merging.",
        "expected": [],
    },
    {
        "id": "financial_data",
        "text": "Account IBAN: FI4950000120000062. Annual salary EUR 85,000. Credit limit $15,000.",
        "expected": [
            ("FINANCIAL", "FI4950000120000062"),
            ("FINANCIAL", "85,000"),
        ],
    },
    {
        "id": "dataset_row_narrative",
        "text": (
            "Leonardo Ferrari, born 06/22/1988, lives at Corso Italia 47, Lombardy, Italy. "
            "Email: leonardo_ferrari@libero.it, phone +39 345 678 9012. "
            "National ID: FRRLRD88H22F205X. Diagnosed with Type 2 diabetes mellitus. "
            "Blood type A+. BRCA2 positive."
        ),
        "expected": [
            ("NAME", "Leonardo Ferrari"),
            ("DOB", "06/22/1988"),
            ("ADDRESS", "Corso Italia 47"),
            ("EMAIL", "leonardo_ferrari@libero.it"),
            ("PHONE", "+39 345 678 9012"),
            ("ID_NUMBER", "FRRLRD88H22F205X"),
        ],
    },
]


N_THREADS = 4  # Keep CPU usage moderate


def evaluate_model(model_path: str, model_name: str) -> dict:
    """Run all test cases against a model and return metrics."""
    print(f"\n{'='*70}")
    print(f"  MODEL: {model_name}")
    print(f"  Path: {model_path}")
    print(f"{'='*70}")

    # Load model
    t0 = time.time()
    reviewer = LLMReviewer(
        model_path=model_path,
        n_threads=N_THREADS,
        use_chat=True,  # Chat mode required — completion mode triggers <think> in Qwen3.5
        include_examples=True,
    )
    # Force model load
    reviewer._load_model()
    load_time = time.time() - t0
    print(f"  Model loaded in {load_time:.1f}s")
    print()

    results = {
        "model": model_name,
        "load_time_s": round(load_time, 1),
        "cases": [],
        "total_expected": 0,
        "total_detected": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "json_parse_failures": 0,
        "total_inference_time_s": 0,
    }

    for case in TEST_CASES:
        t0 = time.time()
        detections = reviewer.review_region(case["text"])
        inference_time = time.time() - t0
        results["total_inference_time_s"] += inference_time

        expected = case["expected"]
        results["total_expected"] += len(expected)
        results["total_detected"] += len(detections)

        # Score: for each expected PII, check if any detection matches the text
        matched_expected = set()
        matched_detected = set()

        for i, (exp_type, exp_text) in enumerate(expected):
            for j, det in enumerate(detections):
                # Match if the detected text contains or is contained by expected
                if (exp_text.lower() in det.text.lower() or
                        det.text.lower() in exp_text.lower()):
                    matched_expected.add(i)
                    matched_detected.add(j)
                    break

        tp = len(matched_expected)
        fn = len(expected) - tp
        fp = len(detections) - len(matched_detected)

        results["true_positives"] += tp
        results["false_negatives"] += fn
        results["false_positives"] += fp

        status = "PASS" if fn == 0 and fp == 0 else "PARTIAL" if tp > 0 else "FAIL" if expected else "PASS"
        if not expected and len(detections) > 0:
            status = "FP"  # False positive on a no-PII case

        det_summary = [(d.text[:30], d.pii_type, f"{d.confidence:.1f}") for d in detections]

        print(f"  [{status:7s}] {case['id']:<30s} | {inference_time:.1f}s | "
              f"expected={len(expected)}, detected={len(detections)}, tp={tp}, fn={fn}, fp={fp}")
        if fn > 0:
            missed = [expected[i] for i in range(len(expected)) if i not in matched_expected]
            for m_type, m_text in missed:
                print(f"           MISSED: ({m_type}) \"{m_text}\"")
        if fp > 0:
            false = [detections[j] for j in range(len(detections)) if j not in matched_detected]
            for f in false:
                print(f"           FALSE+: ({f.pii_type}) \"{f.text[:50]}\" conf={f.confidence:.1f}")

        results["cases"].append({
            "id": case["id"],
            "status": status,
            "inference_time_s": round(inference_time, 2),
            "expected": len(expected),
            "detected": len(detections),
            "true_positives": tp,
            "false_negatives": fn,
            "false_positives": fp,
        })

    # Calculate aggregate metrics
    tp = results["true_positives"]
    fp = results["false_positives"]
    fn = results["false_negatives"]

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    results["precision"] = round(precision, 3)
    results["recall"] = round(recall, 3)
    results["f1"] = round(f1, 3)
    results["avg_inference_time_s"] = round(results["total_inference_time_s"] / len(TEST_CASES), 2)

    print()
    print(f"  METRICS:")
    print(f"    Precision:  {precision:.1%}  (of what it flagged, how much was real PII)")
    print(f"    Recall:     {recall:.1%}  (of all real PII, how much did it find)")
    print(f"    F1 Score:   {f1:.3f}")
    print(f"    Avg time:   {results['avg_inference_time_s']:.2f}s per region")
    print(f"    Total time: {results['total_inference_time_s']:.1f}s for {len(TEST_CASES)} cases")
    print()

    # Cleanup — release model memory
    del reviewer
    return results


def main():
    models_dir = Path(__file__).resolve().parent.parent / "models"

    model_files = {
        "Qwen3.5-0.8B-Q4_K_M": models_dir / "Qwen3.5-0.8B-Q4_K_M.gguf",
        "Qwen3.5-2B-Q4_K_M": models_dir / "Qwen3.5-2B-Q4_K_M.gguf",
        "Qwen3.5-4B-Q4_K_M": models_dir / "Qwen3.5-4B-Q4_K_M.gguf",
    }

    available = {k: v for k, v in model_files.items() if v.exists()}

    if not available:
        print("No models found in models/ directory.")
        print("Download with: python scripts/download_model.py --model 4B --quant Q4_K_M")
        sys.exit(1)

    print(f"Found {len(available)} model(s) to benchmark:")
    for name, path in available.items():
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"  {name}: {size_mb:.0f} MB")
    print(f"\nTest cases: {len(TEST_CASES)}")
    print(f"Total expected PII items: {sum(len(c['expected']) for c in TEST_CASES)}")

    all_results = []
    for name, path in available.items():
        result = evaluate_model(str(path), name)
        all_results.append(result)

    # --- Summary comparison ---
    print()
    print("=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)
    print()
    print(f"  {'Model':<28s} {'Precision':>10s} {'Recall':>8s} {'F1':>8s} {'Avg Time':>10s} {'Load':>8s}")
    print(f"  {'-'*28} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*8}")

    for r in all_results:
        print(
            f"  {r['model']:<28s} "
            f"{r['precision']:>9.1%} "
            f"{r['recall']:>7.1%} "
            f"{r['f1']:>7.3f} "
            f"{r['avg_inference_time_s']:>8.2f}s "
            f"{r['load_time_s']:>6.1f}s"
        )

    print()

    # Save results to JSON
    output_path = Path(__file__).resolve().parent.parent / "tests" / "benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"  Full results saved to: {output_path}")


if __name__ == "__main__":
    main()
