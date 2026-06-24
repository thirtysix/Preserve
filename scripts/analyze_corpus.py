#!/usr/bin/env python3
"""
Error analysis of the deterministic pipeline (aggressive; regex + checksums +
context + name gazetteer, NER off) across corpora.

Corpora:
  ai4privacy  - synthetic, labeled (breadth/per-type at scale)
  tab         - REAL: ECHR court cases, expert-annotated (recall on real prose;
                PERSON->NAME is the cleanest target for us)
  enron       - REAL: business emails, UNLABELED -> false-positive / over-flag
                spot-check (counts + sampled flagged spans + flag density)

Labeled corpora report per-category recall, false negatives by sub-label with
examples, false positives, and the most common unmapped gold labels. Enron
reports detection counts/density and sampled spans for manual precision review.

Writes tests/corpus_errors_<corpus>.json. Read-only.

Usage:
    python scripts/analyze_corpus.py --corpus tab
    python scripts/analyze_corpus.py --corpus enron --n 3000
    python scripts/analyze_corpus.py --corpus ai4privacy --n 10000
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from preserve import Scrubber, PreserveConfig, SensitivityLevel

TESTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")

AI4_MAP = {
    "FIRSTNAME": "NAME", "LASTNAME": "NAME", "MIDDLENAME": "NAME",
    "EMAIL": "EMAIL", "PHONENUMBER": "PHONE", "DOB": "DATE", "DATE": "DATE",
    "STREET": "ADDRESS", "BUILDINGNUMBER": "ADDRESS", "SECONDARYADDRESS": "ADDRESS",
    "ZIPCODE": "ADDRESS", "CREDITCARDNUMBER": "CREDIT_CARD", "IBAN": "IBAN",
    "IPV4": "IP", "IPV6": "IP", "IP": "IP", "SSN": "SSN", "ACCOUNTNUMBER": "ACCOUNT",
}
# TAB entity_type -> our category (PERSON/DATETIME/LOC are what we target;
# CODE/ORG/DEM/QUANTITY/MISC are left unmapped and reported as candidates).
TAB_MAP = {"PERSON": "NAME", "DATETIME": "DATE", "LOC": "ADDRESS"}


def _overlaps(a0, a1, spans):
    return any(a0 < b1 and a1 > b0 for b0, b1 in spans)


def iter_ai4privacy(n, all_langs):
    from datasets import load_dataset
    ds = load_dataset("ai4privacy/pii-masking-200k", split="train", streaming=True)
    c = 0
    for ex in ds:
        if not all_langs and ex.get("language") != "en":
            continue
        gold = [(m["start"], m["end"], AI4_MAP.get(m["label"]), m["value"], m["label"])
                for m in (ex.get("privacy_mask") or [])]
        yield ex.get("source_text") or "", gold
        c += 1
        if c >= n:
            break


def iter_tab(n, all_langs):
    from datasets import load_dataset
    ds = load_dataset("mattmdjaga/text-anonymization-benchmark-train", split="train")
    c = 0
    for ex in ds:
        ann = ex["annotations"]
        if isinstance(ann, str):
            ann = json.loads(ann)
        gold, seen = [], set()
        if isinstance(ann, dict):
            for a in ann.values():            # first annotator only
                if not isinstance(a, dict):
                    continue
                for m in a.get("entity_mentions", []):
                    if m.get("identifier_type") == "NO_MASK":
                        continue
                    key = (m["start_offset"], m["end_offset"])
                    if key in seen:
                        continue
                    seen.add(key)
                    gold.append((m["start_offset"], m["end_offset"],
                                 TAB_MAP.get(m.get("entity_type")), m.get("span_text", ""),
                                 f'{m.get("entity_type")}/{m.get("identifier_type")}'))
                break
        yield ex["text"], gold
        c += 1
        if c >= n:
            break


def iter_enron(n, all_langs):
    from datasets import load_dataset
    ds = load_dataset("corbt/enron-emails", split="train", streaming=True)
    c = 0
    for ex in ds:
        body = (ex.get("body") or "").strip()
        if len(body) < 15:
            continue
        yield body, None        # unlabeled
        c += 1
        if c >= n:
            break


def analyze_labeled(samples, scrubber, examples):
    per_cat = collections.defaultdict(lambda: {"total": 0, "hit": 0})
    miss_by_label = collections.Counter()
    miss_examples = collections.defaultdict(list)
    fp_by_type = collections.Counter()
    fp_examples = collections.defaultdict(list)
    unmapped = collections.Counter()
    n = 0
    for text, gold in samples:
        dets = scrubber.scrub(text).detections
        spans = [(d.start, d.end) for d in dets]
        gold_all = [(s, e) for (s, e, *_ ) in gold]
        for (s, e, cat, value, label) in gold:
            if cat is None:
                unmapped[label.split("/")[0]] += 1
                continue
            per_cat[cat]["total"] += 1
            if _overlaps(s, e, spans):
                per_cat[cat]["hit"] += 1
            else:
                miss_by_label[label] += 1
                if len(miss_examples[cat]) < 400:
                    miss_examples[cat].append((value, label, text[max(0, s - 22):e + 22].replace("\n", " ")))
        for d, (s, e) in zip(dets, spans):
            if not _overlaps(s, e, gold_all):
                fp_by_type[d.replacement_type] += 1
                if len(fp_examples[d.replacement_type]) < 400:
                    fp_examples[d.replacement_type].append((d.matched_text, text[max(0, s - 22):e + 22].replace("\n", " ")))
        n += 1

    print(f"\n{'category':<13s} {'recall':>8s}  hit/total")
    for cat in sorted(per_cat):
        v = per_cat[cat]; r = v["hit"] / v["total"] if v["total"] else 0
        print(f"  {cat:<11s} {r*100:>7.1f}%  {v['hit']}/{v['total']}")
    print("\nFalse negatives by sub-label:")
    for label, c in miss_by_label.most_common(20):
        print(f"  {label:<22s} {c}")
    for cat in sorted(miss_examples):
        print(f"\n  MISS examples [{cat}]:")
        for val, label, ctx in miss_examples[cat][:examples]:
            print(f"    ({label:<16s}) {val!r:26s} …{ctx}…")
    print("\nFalse positives by type:")
    for t, c in fp_by_type.most_common(20):
        print(f"  {t:<14s} {c}")
    for t in sorted(fp_examples):
        print(f"\n  FP examples [{t}]:")
        for val, ctx in fp_examples[t][:examples]:
            print(f"    {val!r:28s} …{ctx}…")
    print("\nMost common UNMAPPED gold labels:")
    for label, c in unmapped.most_common(15):
        print(f"  {label:<18s} {c}")
    return {"n": n, "per_cat": {k: dict(v) for k, v in per_cat.items()},
            "miss_by_label": dict(miss_by_label), "miss_examples": dict(miss_examples),
            "fp_by_type": dict(fp_by_type), "fp_examples": dict(fp_examples),
            "unmapped": dict(unmapped)}


def analyze_unlabeled(samples, scrubber, examples):
    type_counts = collections.Counter()
    type_examples = collections.defaultdict(list)
    total_chars = flagged_chars = with_det = n = 0
    for text, _ in samples:
        dets = scrubber.scrub(text).detections
        total_chars += len(text)
        if dets:
            with_det += 1
        for d in dets:
            flagged_chars += (d.end - d.start)
            type_counts[d.replacement_type] += 1
            if len(type_examples[d.replacement_type]) < 400:
                type_examples[d.replacement_type].append(
                    (d.matched_text, text[max(0, d.start - 22):d.end + 22].replace("\n", " ")))
        n += 1
    print(f"\nUnlabeled FP / over-flag spot-check on {n} real emails (NO labels):")
    print(f"  emails with >=1 detection: {with_det}/{n} ({with_det/n*100:.1f}%)")
    print(f"  flag density: {flagged_chars}/{total_chars} chars = {flagged_chars/max(1,total_chars)*100:.2f}%")
    print(f"  total detections: {sum(type_counts.values())}  ({sum(type_counts.values())/n:.2f}/email)")
    print("\n  detections by type:")
    for t, c in type_counts.most_common():
        print(f"    {t:<14s} {c}")
    for t, _ in type_counts.most_common():
        print(f"\n  sample [{t}] (judge precision by eye):")
        for val, ctx in type_examples[t][:examples]:
            print(f"    {val!r:28s} …{ctx}…")
    return {"n": n, "type_counts": dict(type_counts),
            "flag_density": flagged_chars / max(1, total_chars),
            "emails_with_detection": with_det, "type_examples": dict(type_examples)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", choices=["ai4privacy", "tab", "enron"], default="tab")
    ap.add_argument("--n", type=int, default=0, help="samples (0 = sensible default per corpus)")
    ap.add_argument("--all-langs", action="store_true")
    ap.add_argument("--examples", type=int, default=12)
    args = ap.parse_args()

    defaults = {"ai4privacy": 10000, "tab": 1014, "enron": 3000}
    n = args.n or defaults[args.corpus]
    loaders = {"ai4privacy": iter_ai4privacy, "tab": iter_tab, "enron": iter_enron}

    scrubber = Scrubber(PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE))
    print(f"\nDeterministic error analysis: corpus={args.corpus}, n={n} (aggressive, NER off)\n" + "=" * 66)
    samples = loaders[args.corpus](n, args.all_langs)
    result = (analyze_unlabeled if args.corpus == "enron" else analyze_labeled)(
        samples, scrubber, args.examples)

    out = os.path.join(TESTS, f"corpus_errors_{args.corpus}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
