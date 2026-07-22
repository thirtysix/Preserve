# AGENTS.md

Orientation for AI coding agents (and humans) arriving at this repo: what it is, how to run it, and the conventions worth knowing before making changes.

## What this is
Preserve: local-first, reversible PII detection and scrubbing for LLM prompts. It removes personally identifiable information (and common developer secrets) before text leaves the machine, then restores the original values in the model's response locally. Shipped as the `preserve-pii` PyPI package (import name `preserve`), with a CLI, a Gradio dashboard, an optional OpenAI/Anthropic-compatible gateway, and a static browser demo.

## Stack & layout
- **Core library**: Python 3.10+, package `preserve/` (detectors, patterns, validators, name scorer, scrubber, reversible mapping)
- **Gateway**: FastAPI + uvicorn, app `preserve.api.app:app`, binds 127.0.0.1:8800 (optional `[api]` extra)
- **Dashboard**: Gradio app `dashboard.py`, port 7860
- **Browser demo**: static `docs/` served on GitHub Pages, deterministic layers only
- **Detection layers**: 1) normalcy scanner, 2) regex + domain parsers + checksums + context + hybrid name scorer, 3) optional local LLM review (llama.cpp / llama-cpp-python)

## Run, test, lint
```bash
pip install -e ".[dev,api]"        # from source
python -m preserve scrub "text"    # CLI
python dashboard.py                # Gradio UI on :7860
./scripts/run_api.sh               # gateway on 127.0.0.1:8800
pytest tests/ -q
```

## Conventions
- Raw PII must never leave the machine: only placeholders (`[NAME_1]`) travel to a third-party model. Do not add a code path that sends original values upstream.
- The placeholder map is the reversibility contract; it serializes to JSON so scrub and restore can run in separate processes. In the gateway it is per-request and never persisted.
- Audit logs record detection counts, never PII values. Keep it that way.
- Regex patterns live in `preserve/patterns.py`; the browser demo assets under `docs/assets/` are generated from them, not hand-edited.

## Gotchas
- CI regenerates `docs/assets/patterns.js` and `context.js` via `scripts/export_patterns.py` and fails on any diff. After changing patterns or context scoring, run that script and commit the result.
- The Layer 3 LLM is optional and must run with any "thinking" mode disabled (Preserve does this automatically); the embedded backend is CPU-only, GPU needs the native `llama-server`.
- Gateway rate limiting is in-memory by default and switches to Redis when `REDIS_URL` is set. The bind stays on 127.0.0.1; terminate TLS in a reverse proxy in front.
