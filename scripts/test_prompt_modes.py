#!/usr/bin/env python3
"""
Compare prompt modes: "comprehensive" vs "selected" on 10 test cases.

Tests both modes using the embedded backend (CPU) and measures:
- Detections (what was found)
- Accuracy (true positives vs expected)
- Speed (seconds per call)
- Prompt size (chars)

Usage:
    source .venv/bin/activate
    python -u scripts/test_prompt_modes.py 2>/dev/null
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve.llm_review import LLMReviewer, mark_text, build_chat_prompt

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "Qwen3.5-0.8B-Q4_K_M.gguf",
)

# 10 test cases with expected PII
TEST_CASES = [
    {
        "text": "Patient Aurora Rossi, born 1971-04-05, at Via Roma 31, Helsinki.",
        "spans": [(8, 20), (27, 37), (42, 53)],
        "expected": [("NAME", "Aurora Rossi"), ("DOB", "1971-04-05"), ("ADDRESS", "Via Roma 31")],
    },
    {
        "text": "Employee Pekka Korhonen lives at Mannerheimintie 42.",
        "spans": [(9, 24), (32, 50)],
        "expected": [("NAME", "Pekka Korhonen"), ("ADDRESS", "Mannerheimintie 42")],
    },
    {
        "text": "Client Min-jun Kim, phone +82 10-1234-5678, filed a complaint.",
        "spans": [(7, 18), (26, 42)],
        "expected": [("NAME", "Min-jun Kim"), ("PHONE", "+82 10-1234-5678")],
    },
    {
        "text": "Sofía García at Calle Reforma 156. Salary: MXN 85,000.",
        "spans": [(0, 12), (16, 33), (43, 53)],
        "expected": [("NAME", "Sofía García"), ("ADDRESS", "Calle Reforma 156"), ("FINANCIAL", "MXN 85,000")],
    },
    {
        "text": "João Silva, email joao@example.com, CPF 123.456.789-09.",
        "spans": [(0, 10), (18, 36), (42, 56)],
        "expected": [("NAME", "João Silva"), ("EMAIL", "joao@example.com"), ("ID_NUMBER", "123.456.789-09")],
    },
    {
        "text": "The treatment follows standard guidelines for acute myocardial infarction.",
        "spans": [(20, 40)],
        "expected": [],  # No PII
    },
    {
        "text": "Passport XP4567890 issued in Helsinki. Account FI4950000120000062.",
        "spans": [(9, 18), (47, 63)],
        "expected": [("PASSPORT", "XP4567890"), ("FINANCIAL", "FI4950000120000062")],
    },
    {
        "text": "Dr. Tanaka referred the patient on 15/03/1985.",
        "spans": [(4, 10), (35, 45)],
        "expected": [("NAME", "Tanaka"), ("DOB", "15/03/1985")],
    },
    {
        "text": "Contact Aino Korhonen at +358 44 1234567 for details.",
        "spans": [(8, 22), (26, 41)],
        "expected": [("NAME", "Aino Korhonen"), ("PHONE", "+358 44 1234567")],
    },
    {
        "text": "Blood type A+. Prescribed Metformin 500mg. BRCA2 positive.",
        "spans": [(11, 13), (26, 40), (42, 56)],
        "expected": [],  # No PII — medical data is not PII by itself
    },
]


def score_detections(detections, expected):
    """Score detections against expected PII."""
    tp, fn, fp = 0, 0, 0
    matched = set()

    for exp_type, exp_text in expected:
        found = False
        for j, det in enumerate(detections):
            if j in matched:
                continue
            if (exp_text.lower() in det.text.lower() or
                    det.text.lower() in exp_text.lower()):
                tp += 1
                matched.add(j)
                found = True
                break
        if not found:
            fn += 1

    fp = len(detections) - len(matched)
    return tp, fn, fp


def main():
    print("=" * 70)
    print("  Prompt Mode Comparison: comprehensive vs selected")
    print("=" * 70)
    print()

    modes = ["comprehensive", "selected"]
    results = {}

    for mode in modes:
        print(f"--- Mode: {mode} ---")
        reviewer = LLMReviewer(
            backend="embedded",
            model_path=MODEL_PATH,
            n_threads=4,
            n_threads_batch=4,
            prompt_mode=mode,
        )

        # Warm up
        reviewer.review_text("Test >>>hello<<<.", [(5, 10)])

        total_tp, total_fn, total_fp = 0, 0, 0
        total_time = 0
        total_prompt_chars = 0

        for i, case in enumerate(TEST_CASES, 1):
            # Measure prompt size
            marked, _ = mark_text(case["text"], case["spans"])
            msgs = build_chat_prompt(marked, mode=mode)
            prompt_chars = sum(len(m["content"]) for m in msgs)
            total_prompt_chars += prompt_chars

            # Run inference
            t0 = time.time()
            dets = reviewer.review_text(case["text"], case["spans"])
            elapsed = time.time() - t0
            total_time += elapsed

            tp, fn, fp = score_detections(dets, case["expected"])
            total_tp += tp
            total_fn += fn
            total_fp += fp

            det_list = [(d.pii_type, d.text) for d in dets]
            status = "PASS" if fn == 0 and fp == 0 else "PARTIAL" if tp > 0 else ("FAIL" if case["expected"] else ("FP" if fp > 0 else "PASS"))

            print(
                f"  [{i:2d}] {status:7s} | {elapsed:5.1f}s | "
                f"tp={tp} fn={fn} fp={fp} | "
                f"prompt={prompt_chars:4d}ch | "
                f"{det_list}",
                flush=True,
            )

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        results[mode] = {
            "tp": total_tp, "fn": total_fn, "fp": total_fp,
            "precision": precision, "recall": recall, "f1": f1,
            "total_time": total_time,
            "avg_time": total_time / len(TEST_CASES),
            "avg_prompt_chars": total_prompt_chars / len(TEST_CASES),
        }

        print(f"\n  Precision: {precision:.1%} | Recall: {recall:.1%} | F1: {f1:.3f}")
        print(f"  Avg time: {total_time/len(TEST_CASES):.1f}s | Avg prompt: {total_prompt_chars/len(TEST_CASES):.0f} chars")
        print()

        # Release model between modes
        del reviewer

    # Summary
    print("=" * 70)
    print("  COMPARISON SUMMARY")
    print("=" * 70)
    print()
    print(f"  {'Mode':<20s} {'Precision':>10s} {'Recall':>8s} {'F1':>8s} {'Avg Time':>10s} {'Avg Prompt':>12s}")
    print(f"  {'-'*20} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*12}")
    for mode in modes:
        r = results[mode]
        print(
            f"  {mode:<20s} "
            f"{r['precision']:>9.1%} "
            f"{r['recall']:>7.1%} "
            f"{r['f1']:>7.3f} "
            f"{r['avg_time']:>8.1f}s "
            f"{r['avg_prompt_chars']:>10.0f}ch"
        )


if __name__ == "__main__":
    main()
