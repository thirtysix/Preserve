#!/usr/bin/env python3
"""
Precompute, per demo example, what the local LLM (Layer 3) catches that the
demo's deterministic layers do NOT.

The browser demo cannot run the model, so this script runs the real Python
pipeline offline and bakes the delta into docs/assets/llm_extra.js:

    window.PRESERVE_LLM_EXTRA = {
        "<example name>": [ { "start": int, "end": int, "value": str, "type": str }, ... ],
        ...
    };

"Delta" means: detections the LLM layer (detection_layer == "normalcy+llm")
produced whose character span does NOT overlap anything the demo's own
JavaScript detector already found. That makes the demo's Layer-3 panel show
only genuinely new catches, attributed to the model.

Because a small local model occasionally emits a spurious span, REVIEW the
generated file and prune anything that is not real PII before committing.

Usage:
    python scripts/compute_llm_extra.py                 # uses the 4B model
    PRESERVE_LLM_MODEL=models/Qwen3.5-2B-Q4_K_M.gguf python scripts/compute_llm_extra.py
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")
OUT = os.path.join(ASSETS, "llm_extra.js")
MODEL = os.environ.get("PRESERVE_LLM_MODEL", os.path.join(ROOT, "models", "Qwen3.5-4B-Q4_K_M.gguf"))

# Node snippet: load the demo's own pipeline and emit, per example,
# {text, spans:[[start,end],...]} for the deterministic (aggressive) detections.
_NODE = r"""
global.window = {};
const fs = require('fs'), path = require('path');
const A = process.argv[1];
for (const f of ['names.js','patterns.js','context.js','examples.js'])
  eval(fs.readFileSync(path.join(A, f), 'utf8'));
const app = require(path.join(A, 'app.js'));
const out = {};
for (const [name, text] of Object.entries(window.PRESERVE_EXAMPLES)) {
  const spans = app.detect(text, 'aggressive').map(d => [d.start, d.end]);
  out[name] = { text, spans };
}
process.stdout.write(JSON.stringify(out));
"""


def demo_detections() -> dict:
    res = subprocess.run(
        ["node", "-e", _NODE, ASSETS],
        capture_output=True, text=True, check=True,
    )
    return json.loads(res.stdout)


def overlaps(a0, a1, spans) -> bool:
    return any(a0 < b1 and a1 > b0 for b0, b1 in spans)


def main() -> int:
    if not os.path.exists(MODEL):
        print(f"error: model not found: {MODEL}", file=sys.stderr)
        return 1

    from preserve import Scrubber, PreserveConfig, SensitivityLevel

    examples = demo_detections()
    base = dict(sensitivity_level=SensitivityLevel.AGGRESSIVE, use_name_scorer=True)
    with contextlib.redirect_stderr(open(os.devnull, "w")):
        llm = Scrubber(PreserveConfig(**base, use_llm_review=True,
                                      llm_backend="embedded", llm_model_path=MODEL))

    result: dict[str, list[dict]] = {}
    for name, info in examples.items():
        text, spans = info["text"], info["spans"]
        with contextlib.redirect_stderr(open(os.devnull, "w")):
            dets = llm.scrub(text).detections
        extra = []
        for d in dets:
            if d.detection_layer != "normalcy+llm":
                continue
            if overlaps(d.start, d.end, spans):
                continue
            extra.append({"start": d.start, "end": d.end,
                          "value": d.matched_text, "type": d.replacement_type})
        result[name] = extra
        tag = ", ".join(f"{e['value']!r}->{e['type']}" for e in extra) or "(nothing new)"
        print(f"  {name}: {tag}")

    body = json.dumps(result, ensure_ascii=False, indent=2)
    header = (
        "// Precomputed by scripts/compute_llm_extra.py with a local Qwen3.5 model.\n"
        "// Per example: PII the local LLM (Layer 3) catches that the demo's\n"
        "// deterministic layers miss. Reviewed by hand; the browser can't run the model.\n"
    )
    # A friendly model label for the demo, e.g. "Qwen3.5-4B (Q4_K_M)".
    stem = os.path.splitext(os.path.basename(MODEL))[0]
    label = stem.replace("-Q4_K_M", " (Q4_K_M)").replace("-Q8_0", " (Q8_0)")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(f"window.PRESERVE_LLM_MODEL = {json.dumps(label)};\n")
        fh.write("window.PRESERVE_LLM_EXTRA = ")
        fh.write(body)
        fh.write(";\n")
    print(f"wrote {OUT} (model: {os.path.basename(MODEL)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
