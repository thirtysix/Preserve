#!/usr/bin/env python3
"""
A/B experiment: does PII representation affect the upstream LLM's answer quality?

Compares three ways of presenting PII to the model, on the SAME instances:
  raw         - real values (ceiling: no privacy)
  placeholder - [NAME_1], [DATE_1], ... then restore
  surrogate   - realistic fake values, then restore

Across three task families with programmatic ground truth:
  carry_through - the model must carry an entity through (name + email in output)
  numeric       - the model must compute on a value (sum of two amounts)
  date          - the model must reason on a value (age >= 18 from a DOB)

For the value families each wrong answer is classified as 'wrong' (a definite,
incorrect answer) or 'abstain' (no parseable answer / explicit cannot), to show
the failure MODE: surrogates tend to fail silently wrong, placeholders fail safe.

Entities are authored directly here (no detector), to isolate the representation
choice. Uses the native llama-server (GPU) with the 4B model.

Usage:
    python scripts/experiment_surrogate.py --n 12
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_llm import _start_server, _stop_server, SERVER_BIN  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "models", "Qwen3.5-4B-Q4_K_M.gguf")
PORT = 8090
TODAY = dt.date(2026, 6, 24)

REAL_NAMES = [
    "James Wilson", "Mary Johnson", "Robert Davis", "Patricia Miller", "Linda Garcia",
    "Michael Anderson", "Barbara Thomas", "William Martinez", "Elizabeth Clark", "David Lewis",
    "Susan Walker", "Joseph Hall", "Karen Young", "Charles King", "Nancy Wright",
]
SURR_NAMES = [
    "Tomas Novak", "Aiko Tanaka", "Nadia Haddad", "Olof Berg", "Priya Nair",
    "Mateo Rossi", "Ingrid Larsen", "Kenji Sato", "Amara Okoye", "Lukas Vogel",
    "Yara Mansour", "Sofia Marchetti", "Diego Herrera", "Hana Kim", "Erik Lindqvist",
]


def _email(name: str, dom: str) -> str:
    return name.lower().replace(" ", ".") + "@" + dom


def _age(dob: dt.date, today: dt.date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _num(s: str):
    m = re.search(r"-?\d[\d,]*\.?\d*", s.replace("$", ""))
    return float(m.group().replace(",", "")) if m else None


def _yesno(s: str):
    sl = s.lower()
    has_y, has_n = re.search(r"\byes\b", sl), re.search(r"\bno\b", sl)
    if has_y and not has_n:
        return True
    if has_n and not has_y:
        return False
    return None


def build_instances(n: int) -> list[dict]:
    """Each instance carries the three representations + ground truth + a grader."""
    insts = []
    for i in range(n):
        rn, sn = REAL_NAMES[i % len(REAL_NAMES)], SURR_NAMES[i % len(SURR_NAMES)]
        re_, se_ = _email(rn, "example.com"), _email(sn, "example.org")

        # carry_through
        tmpl = "Write a one-sentence appointment confirmation for {name} ({email}). Output only the sentence."
        insts.append({
            "family": "carry_through",
            "prompts": {
                "raw": tmpl.format(name=rn, email=re_),
                "placeholder": tmpl.format(name="[NAME_1]", email="[EMAIL_1]"),
                "surrogate": tmpl.format(name=sn, email=se_),
            },
            "restore": {
                "raw": {},
                "placeholder": {"[NAME_1]": rn, "[EMAIL_1]": re_},
                "surrogate": {sn: rn, se_: re_},
            },
            "grade": ("contains", (rn.lower(), re_.lower())),
        })

        # numeric: sum of two amounts
        ra, rb = 1000 + i * 137, 500 + i * 211
        sa, sb = 3000 + i * 91, 1700 + i * 173
        tmpl = "What is the sum of {a} and {b} US dollars? Respond with only the number, no words or symbols."
        insts.append({
            "family": "numeric",
            "prompts": {
                "raw": tmpl.format(a=ra, b=rb),
                "placeholder": tmpl.format(a="[AMOUNT_1]", b="[AMOUNT_2]"),
                "surrogate": tmpl.format(a=sa, b=sb),
            },
            "restore": {"raw": {}, "placeholder": {}, "surrogate": {}},
            "grade": ("number", float(ra + rb)),
        })

        # date: age >= 18
        rdob = dt.date(2000 + (i % 25), 1 + i % 12, 1 + i % 27)   # spans under/over 18
        sdob = dt.date(1960 + (i * 3 % 50), 1 + (i + 4) % 12, 1 + (i + 7) % 27)
        tmpl = ("Given the date of birth {dob} and today's date " + TODAY.isoformat() +
                ", is the person at least 18 years old? Answer with only 'yes' or 'no'.")
        insts.append({
            "family": "date",
            "prompts": {
                "raw": tmpl.format(dob=rdob.isoformat()),
                "placeholder": tmpl.format(dob="[DOB_1]"),
                "surrogate": tmpl.format(dob=sdob.isoformat()),
            },
            "restore": {"raw": {}, "placeholder": {}, "surrogate": {}},
            "grade": ("yesno", _age(rdob, TODAY) >= 18),
        })
    return insts


def grade(kind, gt, answer: str):
    """Return (correct: bool, mode: 'correct'|'wrong'|'abstain')."""
    if kind == "contains":
        ok = all(tok in answer.lower() for tok in gt)
        return ok, ("correct" if ok else "wrong")
    if kind == "number":
        v = _num(answer)
        if v is None:
            return False, "abstain"
        return (abs(v - gt) < 0.5), ("correct" if abs(v - gt) < 0.5 else "wrong")
    if kind == "yesno":
        v = _yesno(answer)
        if v is None:
            return False, "abstain"
        return (v == gt), ("correct" if v == gt else "wrong")
    return False, "abstain"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="instances per task family")
    args = ap.parse_args()

    if not os.path.exists(MODEL) or not SERVER_BIN.exists():
        print("error: need the 4B model and llama-server", file=sys.stderr)
        return 1

    from openai import OpenAI
    insts = build_instances(args.n)
    families = ["carry_through", "numeric", "date"]
    conditions = ["raw", "placeholder", "surrogate"]
    # tallies[family][condition] = {"correct":x,"wrong":y,"abstain":z}
    tallies = {f: {c: {"correct": 0, "wrong": 0, "abstain": 0} for c in conditions} for f in families}

    print(f"Starting llama-server (4B, GPU)...")
    proc = _start_server(MODEL, PORT, 99)
    try:
        client = OpenAI(base_url=f"http://127.0.0.1:{PORT}/v1", api_key="x")
        total = len(insts) * len(conditions)
        done = 0
        for inst in insts:
            for cond in conditions:
                prompt = inst["prompts"][cond]
                resp = client.chat.completions.create(
                    model="local", temperature=0.0, max_tokens=80,
                    messages=[{"role": "user", "content": prompt}],
                )
                ans = (resp.choices[0].message.content or "")
                for surr, real in inst["restore"][cond].items():
                    ans = ans.replace(surr, real)
                kind, gt = inst["grade"]
                _, mode = grade(kind, gt, ans)
                tallies[inst["family"]][cond][mode] += 1
                done += 1
            print(f"  {done}/{total}", end="\r")
    finally:
        _stop_server(proc)

    print("\n\n" + "=" * 66)
    print(f"  SURROGATE vs PLACEHOLDER vs RAW  (n={args.n}/family, 4B, temp 0)")
    print("=" * 66)
    n = args.n
    for f in families:
        print(f"\n{f}")
        print(f"    {'condition':<12s} {'accuracy':>9s}   {'correct/wrong/abstain'}")
        for c in conditions:
            t = tallies[f][c]
            acc = t["correct"] / n if n else 0
            print(f"    {c:<12s} {acc*100:>8.0f}%   {t['correct']}/{t['wrong']}/{t['abstain']}")

    import json
    out = os.path.join(ROOT, "tests", "experiment_surrogate.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"n": args.n, "model": os.path.basename(MODEL), "tallies": tallies}, fh, indent=2)
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
