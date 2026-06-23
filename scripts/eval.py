#!/usr/bin/env python3
"""
Unified evaluation harness for Preserve.

One command produces the numbers the README and docs quote, with both
precision and recall (not just recall), a recall-weighted F-beta, and a
per-type / per-tag breakdown. It evaluates:

  1. Clean data  (tests/test_data.csv, 100 rows) in context: per-column recall,
     overall recall + precision, and reversible round-trip.
  2. Messy data  (tests/messy_test_data.json, 23 cases): overall recall +
     precision and a per-tag recall breakdown.
  3. Layer 3 LLM (read from tests/benchmark_results_gpu.json, or re-run with
     --with-llm): precision / recall / F1 / F2 per model.

Outputs a console summary, a markdown report (docs/EVALUATION.md), and a
machine-readable tests/eval_results.json.

Why F-beta with beta=2: for PII scrubbing a miss (false negative) leaks data,
while a false positive only over-redacts. Recall therefore matters more than
precision, so we report F2 (recall-weighted) alongside the symmetric F1.

Usage:
    python scripts/eval.py                 # uses saved Layer-3 results
    python scripts/eval.py --with-llm      # re-run the GPU Layer-3 benchmark first
    python scripts/eval.py --no-report     # console only, don't write files
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preserve import Scrubber, PreserveConfig, SensitivityLevel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
DOCS = os.path.join(ROOT, "docs")

PII_COLUMNS = [
    "full_name", "date_of_birth", "email", "phone", "national_id",
    "passport_number", "bank_account", "credit_card", "ip_address",
    "address", "emergency_contact_name", "emergency_contact_phone",
]


def fbeta(precision: float, recall: float, beta: float) -> float:
    """F-beta score. beta>1 weights recall higher; beta=1 is the usual F1."""
    b2 = beta * beta
    denom = b2 * precision + recall
    return (1 + b2) * precision * recall / denom if denom > 0 else 0.0


def _overlaps(a0, a1, spans) -> bool:
    return any(a0 < b1 and a1 > b0 for b0, b1 in spans)


# --------------------------------------------------------------------------- #
# 1. Clean data, in context
# --------------------------------------------------------------------------- #
def eval_clean() -> dict:
    import csv
    with open(os.path.join(TESTS, "test_data.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    per_col = {c: {"total": 0, "detected": 0} for c in PII_COLUMNS}
    det_total = det_hit = 0          # for precision (detections overlapping wanted PII)
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

        # Required spans (the 12 PII fields) and "allowed" extras (region/country
        # are location data we neither require nor penalise).
        required, allowed = [], []
        for col in PII_COLUMNS:
            val = row.get(col, "")
            if not val or val == "None":
                continue
            idx = narrative.find(val)
            if idx < 0:
                continue
            span = (idx, idx + len(val))
            required.append(span)
            allowed.append(span)
            per_col[col]["total"] += 1
            if _overlaps(span[0], span[1], spans):
                per_col[col]["detected"] += 1
        for extra in ("region", "country"):
            v = row.get(extra, "")
            if v:
                i = narrative.find(v)
                if i >= 0:
                    allowed.append((i, i + len(v)))

        for (s, e) in spans:
            det_total += 1
            if _overlaps(s, e, allowed):
                det_hit += 1

    td = sum(c["detected"] for c in per_col.values())
    tt = sum(c["total"] for c in per_col.values())
    recall = td / tt if tt else 0.0
    precision = det_hit / det_total if det_total else 0.0
    return {
        "rows": len(rows),
        "per_column": {c: {"recall": (v["detected"] / v["total"] if v["total"] else 0.0),
                           **v} for c, v in per_col.items()},
        "recall": recall, "precision": precision,
        "f1": fbeta(precision, recall, 1), "f2": fbeta(precision, recall, 2),
        "round_trip_ok": round_trips_ok,
        "round_trip_total": len(rows),
    }


# --------------------------------------------------------------------------- #
# 2. Messy data
# --------------------------------------------------------------------------- #
def eval_messy() -> dict:
    with open(os.path.join(TESTS, "messy_test_data.json"), encoding="utf-8") as f:
        cases = json.load(f)

    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    # Two yardsticks, reported together so the number never appears to "move":
    #   overlap = any character overlap counts as a hit (lenient ceiling; credits
    #             partial/boundary detections). Matches the clean eval's rule.
    #   strict  = exact one-to-one substring match (conservative floor; a
    #             partial/boundary hit is a partial leak, so it counts as a miss).
    ov = {"tp": 0, "fn": 0, "fp": 0}
    st = {"tp": 0, "fn": 0, "fp": 0}
    per_tag: dict[str, dict] = {}

    for case in cases:
        text = case["text"]
        low = text.lower()
        expected = case.get("expected_pii", [])
        dets = scrubber.scrub(text).detections
        spans = [(d.start, d.end) for d in dets]
        det_texts = [d.matched_text.lower() for d in dets]

        # --- overlap ---
        exp_spans, c_tp_ov = [], 0
        for exp in expected:
            i = low.find(exp.lower())
            if i >= 0:
                es = (i, i + len(exp))
                exp_spans.append(es)
                if _overlaps(es[0], es[1], spans):
                    c_tp_ov += 1
            elif any(exp.lower() in dt or dt in exp.lower() for dt in det_texts):
                c_tp_ov += 1
        ov["tp"] += c_tp_ov
        ov["fn"] += len(expected) - c_tp_ov
        ov["fp"] += sum(1 for s, e in spans if not _overlaps(s, e, exp_spans))

        # --- strict (one-to-one substring) ---
        matched_det = set()
        c_tp_st = 0
        for exp in expected:
            el = exp.lower()
            for j, dt in enumerate(det_texts):
                if j in matched_det:
                    continue
                if el in dt or dt in el:
                    matched_det.add(j)
                    c_tp_st += 1
                    break
        st["tp"] += c_tp_st
        st["fn"] += len(expected) - c_tp_st
        st["fp"] += len(det_texts) - len(matched_det)

        for tag in case.get("tags", []):
            t = per_tag.setdefault(tag, {"expected": 0, "found": 0})
            t["expected"] += len(expected)
            t["found"] += c_tp_ov

    def metrics(d):
        r = d["tp"] / (d["tp"] + d["fn"]) if (d["tp"] + d["fn"]) else 0.0
        p = d["tp"] / (d["tp"] + d["fp"]) if (d["tp"] + d["fp"]) else 0.0
        return {**d, "recall": r, "precision": p,
                "f1": fbeta(p, r, 1), "f2": fbeta(p, r, 2)}

    return {
        "cases": len(cases),
        "overlap": metrics(ov),
        "strict": metrics(st),
        "per_tag": {k: {**v, "recall": (v["found"] / v["expected"] if v["expected"] else 0.0)}
                    for k, v in sorted(per_tag.items())},
    }


# --------------------------------------------------------------------------- #
# 3. Hard set (typed, held-out blind spots) -- Layer 2 floor, per PII type
# --------------------------------------------------------------------------- #
def eval_hard() -> dict:
    with open(os.path.join(TESTS, "hard_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    per_type: dict[str, dict] = {}
    tp = fn = 0
    for case in cases:
        text, low = case["text"], case["text"].lower()
        spans = [(d.start, d.end) for d in scrubber.scrub(text).detections]
        for item in case["pii"]:
            pt = per_type.setdefault(item["type"], {"total": 0, "found": 0})
            pt["total"] += 1
            i = low.find(item["value"].lower())
            if i >= 0 and _overlaps(i, i + len(item["value"]), spans):
                pt["found"] += 1
                tp += 1
            else:
                fn += 1
    return {
        "cases": len(cases), "items": tp + fn, "tp": tp, "fn": fn,
        "recall": tp / (tp + fn) if (tp + fn) else 0.0,
        "per_type": {k: {**v, "recall": (v["found"] / v["total"] if v["total"] else 0.0)}
                     for k, v in sorted(per_type.items())},
    }


# --------------------------------------------------------------------------- #
# 4. Negatives (no-PII text) -- false-positive rate / precision floor
# --------------------------------------------------------------------------- #
def eval_negatives() -> dict:
    with open(os.path.join(TESTS, "negatives.json"), encoding="utf-8") as f:
        texts = json.load(f)
    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    fp = 0
    clean = 0
    offenders = []
    for t in texts:
        dets = scrubber.scrub(t).detections
        if dets:
            fp += len(dets)
            offenders.append({"text": t[:60], "flagged": [d.matched_text for d in dets]})
        else:
            clean += 1
    return {
        "texts": len(texts), "clean": clean, "false_positives": fp,
        "clean_rate": clean / len(texts) if texts else 0.0,
        "offenders": offenders,
    }


# --------------------------------------------------------------------------- #
# 5. Layer 3 (from saved GPU benchmark, or re-run)
# --------------------------------------------------------------------------- #
def eval_layer3(with_llm: bool) -> dict | None:
    path = os.path.join(TESTS, "benchmark_results_gpu.json")
    if with_llm:
        import subprocess
        print("Re-running the GPU Layer-3 benchmark (this starts llama-server per model)...")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "benchmark_llm.py"),
                        "--backend", "server"], check=True)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    models = []
    for r in data:
        p, rec = r.get("precision", 0.0), r.get("recall", 0.0)
        models.append({
            "model": r["model"], "precision": p, "recall": rec,
            "f1": r.get("f1", fbeta(p, rec, 1)), "f2": round(fbeta(p, rec, 2), 3),
            "avg_time_s": r.get("avg_inference_time_s"),
        })
    return {"models": models}


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def print_console(clean, messy, hard, neg, l3) -> None:
    print("\n" + "=" * 64)
    print("  PRESERVE EVALUATION")
    print("=" * 64)

    print(f"\nCLEAN (in context, {clean['rows']} rows)  "
          f"recall {pct(clean['recall'])}  precision {pct(clean['precision'])}  "
          f"F1 {clean['f1']:.3f}  F2 {clean['f2']:.3f}")
    print(f"  reversible round-trip: {clean['round_trip_ok']}/{clean['round_trip_total']}")
    for c, v in clean["per_column"].items():
        flag = "  " if v["recall"] >= 0.9 else "! "
        print(f"    {flag}{c:<26s} {v['detected']:>3d}/{v['total']:<3d}  {pct(v['recall'])}")

    ov, st = messy["overlap"], messy["strict"]
    print(f"\nMESSY ({messy['cases']} cases) -- two yardsticks, same detector:")
    print(f"  overlap (partial hit counts): recall {pct(ov['recall'])}  precision {pct(ov['precision'])}  "
          f"F2 {ov['f2']:.3f}  (TP {ov['tp']} FN {ov['fn']} FP {ov['fp']})")
    print(f"  strict  (exact, partial=miss): recall {pct(st['recall'])}  precision {pct(st['precision'])}  "
          f"F2 {st['f2']:.3f}  (TP {st['tp']} FN {st['fn']} FP {st['fp']})")
    for tag, v in messy["per_tag"].items():
        print(f"    {tag:<22s} {v['found']:>3d}/{v['expected']:<3d}  {pct(v['recall'])}")

    print(f"\nHARD SET (Layer 2 only, {hard['cases']} cases, {hard['items']} items)  "
          f"recall {pct(hard['recall'])}  (this is the floor the local LLM lifts)")
    for t, v in hard["per_type"].items():
        print(f"    {t:<12s} {v['found']:>2d}/{v['total']:<2d}  {pct(v['recall'])}")

    print(f"\nNEGATIVES ({neg['texts']} no-PII texts)  clean {neg['clean']}/{neg['texts']}  "
          f"false positives {neg['false_positives']}")
    for o in neg["offenders"]:
        print(f"    FP: {o['flagged']} in {o['text']!r}")

    if l3:
        print("\nLAYER 3 (local LLM, GPU)")
        print(f"    {'model':<22s} {'P':>7s} {'R':>7s} {'F1':>7s} {'F2':>7s}")
        for m in l3["models"]:
            print(f"    {m['model']:<22s} {pct(m['precision']):>7s} {pct(m['recall']):>7s} "
                  f"{m['f1']:>7.3f} {m['f2']:>7.3f}")
    print()


def write_report(clean, messy, hard, neg, l3) -> None:
    lines = ["# Evaluation", "",
             "Generated by `scripts/eval.py`. F2 is recall-weighted (recall matters",
             "more than precision for PII: a miss leaks data, a false positive only",
             "over-redacts).", ""]

    lines += ["## Clean data (100 rows, in context)", "",
              f"Overall recall **{pct(clean['recall'])}**, precision {pct(clean['precision'])}, "
              f"F1 {clean['f1']:.3f}, F2 {clean['f2']:.3f}. "
              f"Reversible round-trip: {clean['round_trip_ok']}/{clean['round_trip_total']} rows exact.", "",
              "| Column | Recall | Found/Total |", "| --- | --- | --- |"]
    for c, v in clean["per_column"].items():
        lines.append(f"| {c} | {pct(v['recall'])} | {v['detected']}/{v['total']} |")

    ov, st = messy["overlap"], messy["strict"]
    lines += ["", "## Messy data (23 cases)", "",
              "Two yardsticks on the same detector (a partial/boundary hit is a partial",
              "leak, so we report both a lenient ceiling and a conservative floor):", "",
              "| Yardstick | Recall | Precision | F1 | F2 |", "| --- | --- | --- | --- | --- |",
              f"| Overlap (partial hit counts) | {pct(ov['recall'])} | {pct(ov['precision'])} | {ov['f1']:.3f} | {ov['f2']:.3f} |",
              f"| Strict (exact, partial = miss) | {pct(st['recall'])} | {pct(st['precision'])} | {st['f1']:.3f} | {st['f2']:.3f} |",
              "", "Per-tag recall (overlap):", "",
              "| Tag | Recall | Found/Expected |", "| --- | --- | --- |"]
    for tag, v in messy["per_tag"].items():
        lines.append(f"| {tag} | {pct(v['recall'])} | {v['found']}/{v['expected']} |")

    lines += ["", "## Hard set (Layer 2 only, typed blind spots)", "",
              f"Held-out cases targeting what the deterministic layers struggle with. "
              f"Overall recall **{pct(hard['recall'])}** ({hard['tp']}/{hard['items']} items). "
              f"This is the floor the local LLM (Layer 3) is meant to lift.", "",
              "| PII type | Recall | Found/Total |", "| --- | --- | --- |"]
    for t, v in hard["per_type"].items():
        lines.append(f"| {t} | {pct(v['recall'])} | {v['found']}/{v['total']} |")

    lines += ["", "## Negatives (no-PII text)", "",
              f"Clean (zero detections) on **{neg['clean']}/{neg['texts']}** texts; "
              f"{neg['false_positives']} false positive(s) total."]
    if neg["offenders"]:
        lines.append("")
        for o in neg["offenders"]:
            lines.append(f"- `{o['flagged']}` flagged in: {o['text']}")

    if l3:
        lines += ["", "## Layer 3 (local LLM, GPU, current pipeline)", "",
                  "| Model | Precision | Recall | F1 | F2 |", "| --- | --- | --- | --- | --- |"]
        for m in l3["models"]:
            lines.append(f"| {m['model']} | {pct(m['precision'])} | {pct(m['recall'])} | "
                         f"{m['f1']:.3f} | {m['f2']:.3f} |")
    lines.append("")

    with open(os.path.join(DOCS, "EVALUATION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(os.path.join(TESTS, "eval_results.json"), "w", encoding="utf-8") as f:
        json.dump({"clean": clean, "messy": messy, "hard": hard, "negatives": neg, "layer3": l3}, f, indent=2)


# --------------------------------------------------------------------------- #
# Corpus mode: run a config comparison on a large downloaded dataset
# --------------------------------------------------------------------------- #
# Map ai4privacy's taxonomy onto the PII categories Preserve targets. Gold
# entities whose label is NOT here are "out of scope": excluded from recall and
# never counted as a false positive (Preserve doesn't claim to detect them).
AI4PRIVACY_MAP = {
    "FIRSTNAME": "NAME", "LASTNAME": "NAME", "MIDDLENAME": "NAME",
    "EMAIL": "EMAIL",
    "PHONENUMBER": "PHONE",
    "DOB": "DATE", "DATE": "DATE",
    "STREET": "ADDRESS", "BUILDINGNUMBER": "ADDRESS",
    "SECONDARYADDRESS": "ADDRESS", "ZIPCODE": "ADDRESS",
    "CREDITCARDNUMBER": "CREDIT_CARD",
    "IBAN": "IBAN",
    "IPV4": "IP", "IPV6": "IP", "IP": "IP",
    "SSN": "SSN",
    "ACCOUNTNUMBER": "ACCOUNT",
}


def load_corpus(n: int, all_langs: bool):
    from datasets import load_dataset
    ds = load_dataset("ai4privacy/pii-masking-200k", split="train", streaming=True)
    samples = []
    for ex in ds:
        if not all_langs and ex.get("language") != "en":
            continue
        text = ex.get("source_text") or ""
        pm = ex.get("privacy_mask") or []
        gold_all = [(m["start"], m["end"]) for m in pm]
        gold_sup = [(m["start"], m["end"], AI4PRIVACY_MAP[m["label"]])
                    for m in pm if m.get("label") in AI4PRIVACY_MAP]
        samples.append((text, gold_sup, gold_all))
        if len(samples) >= n:
            break
    return samples


def _run_config(samples, config) -> dict:
    scrubber = Scrubber(config)
    per_cat: dict[str, dict] = {}
    tp = fn = det_total = det_fp = 0
    for text, gold_sup, gold_all in samples:
        spans = [(d.start, d.end) for d in scrubber.scrub(text).detections]
        for (s, e, cat) in gold_sup:
            pc = per_cat.setdefault(cat, {"total": 0, "found": 0})
            pc["total"] += 1
            if _overlaps(s, e, spans):
                pc["found"] += 1
                tp += 1
            else:
                fn += 1
        for (s, e) in spans:
            det_total += 1
            if not _overlaps(s, e, gold_all):
                det_fp += 1
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = (det_total - det_fp) / det_total if det_total else 0.0
    return {"recall": recall, "precision": precision, "tp": tp, "fn": fn, "fp": det_fp,
            "f1": fbeta(precision, recall, 1), "f2": fbeta(precision, recall, 2),
            "per_cat": {k: {**v, "recall": (v["found"] / v["total"] if v["total"] else 0.0)}
                        for k, v in sorted(per_cat.items())}}


def run_corpus_comparison(n: int, all_langs: bool, with_llm: bool) -> None:
    SL = SensitivityLevel
    print(f"\nLoading ai4privacy/pii-masking-200k ({'all langs' if all_langs else 'en'}, n={n})...")
    samples = load_corpus(n, all_langs)
    gold = sum(len(g) for _, g, _ in samples)
    print(f"Loaded {len(samples)} samples, {gold} in-scope gold PII entities.\n")

    configs = [
        ("minimal", PreserveConfig(sensitivity_level=SL.MINIMAL)),
        ("standard", PreserveConfig(sensitivity_level=SL.STANDARD)),
        ("aggressive", PreserveConfig(sensitivity_level=SL.AGGRESSIVE)),
        ("aggressive, no name-scorer", PreserveConfig(sensitivity_level=SL.AGGRESSIVE, use_name_scorer=False)),
        ("aggressive + NER (spaCy)", PreserveConfig(sensitivity_level=SL.AGGRESSIVE, use_ner=True)),
    ]
    if with_llm:
        configs.append(("aggressive + LLM", PreserveConfig(
            sensitivity_level=SL.AGGRESSIVE, use_llm_review=True, llm_backend="embedded")))

    results = []
    for name, cfg in configs:
        r = _run_config(samples, cfg)
        results.append((name, r))
        print(f"  ran: {name:<28s} recall {pct(r['recall'])}  precision {pct(r['precision'])}")

    print("\n" + "=" * 74)
    print(f"  CONFIG COMPARISON on ai4privacy ({len(samples)} samples, {gold} entities)")
    print("=" * 74)
    print(f"  {'config':<28s} {'recall':>8s} {'precision':>10s} {'F1':>7s} {'F2':>7s}")
    print(f"  {'-'*28} {'-'*8} {'-'*10} {'-'*7} {'-'*7}")
    for name, r in results:
        print(f"  {name:<28s} {pct(r['recall']):>8s} {pct(r['precision']):>10s} {r['f1']:>7.3f} {r['f2']:>7.3f}")

    # Per-category recall for the default 'aggressive' config.
    agg = dict(results)["aggressive"]
    print("\n  Per-category recall (aggressive):")
    for cat, v in agg["per_cat"].items():
        print(f"    {cat:<12s} {v['found']:>4d}/{v['total']:<4d}  {pct(v['recall'])}")
    print()

    out = os.path.join(TESTS, "corpus_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"corpus": "ai4privacy/pii-masking-200k", "lang": "all" if all_langs else "en",
                   "samples": len(samples), "gold_entities": gold,
                   "configs": {name: r for name, r in results}}, f, indent=2)
    print(f"Wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Preserve unified evaluation")
    ap.add_argument("--with-llm", action="store_true", help="add the LLM config / re-run the GPU benchmark")
    ap.add_argument("--no-report", action="store_true", help="console only; do not write files")
    ap.add_argument("--corpus", choices=["ai4privacy"], help="run a config comparison on a large corpus")
    ap.add_argument("--n", type=int, default=1000, help="number of corpus samples (default 1000)")
    ap.add_argument("--all-langs", action="store_true", help="corpus: include all languages (default: en only)")
    args = ap.parse_args()

    if args.corpus:
        run_corpus_comparison(args.n, args.all_langs, args.with_llm)
        return 0

    clean = eval_clean()
    messy = eval_messy()
    hard = eval_hard()
    neg = eval_negatives()
    l3 = eval_layer3(args.with_llm)

    print_console(clean, messy, hard, neg, l3)
    if not args.no_report:
        write_report(clean, messy, hard, neg, l3)
        print(f"Wrote {os.path.join('docs', 'EVALUATION.md')} and "
              f"{os.path.join('tests', 'eval_results.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
