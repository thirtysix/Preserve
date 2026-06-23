# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [0.4.0] - 2026-06-23

### Added
- **Unified evaluation harness** (`scripts/eval.py` -> `docs/EVALUATION.md`): precision **and**
  recall, recall-weighted F2, per-column and per-tag breakdowns, and a Layer-3 summary.
- **Browser demo overhaul**: full-bleed dashboard layout; a compact **gazetteer name scorer**
  (55 countries) that catches bare international names; a **"With a local LLM (Layer 3)"**
  panel showing what the model catches beyond the rules (precomputed offline by
  `scripts/compute_llm_extra.py`, since the browser runs no model); a live "what each
  sensitivity applies" detail line.
- **GPU benchmark backend**: `scripts/benchmark_llm.py --backend server` runs the suite
  against the native `llama-server` (full GPU offload).
- **Workflows** section in the README (app integration, reversible cross-process scrub/
  restore, dataset de-identification, detect-only CI audit, team gateway).
- `pyproject.toml` packaging with a `preserve` console-script entry point.

### Changed
- **Recommended Layer 3 model is now Qwen3.5-4B** (was 0.8B). A fair GPU re-run on the
  current pipeline shows the 4B is best by a wide margin (F1 0.847 vs 0.485 for 0.8B); the
  earlier "0.8B is best" ranking was a stale-benchmark artifact. `config.py` default updated.
- **Honest performance reporting**: clean-data precision (99.9%) is now reported alongside
  recall (99.8%); messy-data recall is given as dual bounds (80.5% strict to 90.2% overlap)
  so the figure does not appear to drift with the scoring rule.
- Migrated from `setup.py` to `pyproject.toml`; distribution name is `preserve-pii`
  (import name remains `preserve`).
- All documentation is em-dash and emoji free.

### Fixed
- Demo placeholder numbering now runs left-to-right (document order).
- The Finnish demo record's patient name ("Mikko Virtanen") is now caught by the demo's
  name scorer.

## [0.3.0] - 2026-06-22

### Added
- Initial public release: three-layer PII detection library (regex + checksums + context +
  gazetteer name scorer, optional local LLM review), CLI (`python -m preserve`), Gradio
  dashboard, OpenAI-compatible API gateway with auth/quotas/audit, a 100% client-side static
  browser demo, CI on Python 3.11/3.12, and Docker/Redis deployment artifacts.
