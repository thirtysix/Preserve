# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [0.5.2] - 2026-06-24

Error analysis on real corpora (TAB ECHR court cases, Enron email) plus synthetic
ai4privacy drove a precision + recall pass. New tool: `scripts/analyze_corpus.py`.

### Fixed (precision)
- `bank_contextual` no longer fires inside words ("accountant", "bankruptcy") or
  captures arbitrary trailing text; it now requires a digit-led, account-number-like
  value. FINANCIAL false positives essentially eliminated (Enron 417 -> 2, TAB ~798 -> 0).
- Relative/fuzzy date references ("tomorrow", "yesterday", "3 years", "one year after")
  and runaway spans are no longer tagged as dates of birth (DOB false positives roughly
  halved on Enron; ~99% cut on ai4privacy).

### Added (recall)
- International names: the name tokenizer now spans Latin Extended-A (Polish, Turkish,
  Czech, ...), recovering names like "Sarı", "Çolak", "İlhan Karakurt", "Stępniak"
  (TAB NAME recall 65.9% -> 71.5%).
- Month-name dates ("14 June 1994", "February 4, 1909"), year-anchored to stay precise.
- Secondary-address units ("Apt. 259", "Suite 786", "Unit 4B") (ADDRESS recall on
  ai4privacy 54.9% -> 74.7%).

### Changed
- Tightening `bank_contextual` for precision slightly lowers bare ACCOUNT-number recall;
  net positive given the false-positive elimination.

## [0.5.1] - 2026-06-24

### Fixed
- Bare clock times (e.g. `12:34:56`, `23:59 today`) are no longer misread as a date of birth.
- MAC-style hex (`aa:bb:cc:dd:ee:ff`) is no longer flagged as a name (the gazetteer pair pass
  no longer spans punctuation like `:`).

### Changed
- Docs: the README and live demo now reflect the full 65-pattern set, the secrets/credential
  category, and IPv6. (The 0.5.0 PyPI page predated these doc updates; this release refreshes it.)

## [0.5.0] - 2026-06-24

### Added
- **IPv6 detection** (full, compressed, IPv4-mapped, zone id) and alphanumeric house
  numbers, taking corpus IP recall from 52% to 100% and overall aggressive recall from
  66.8% to 72.8%.
- **Secrets / credential detection** (new `SECRET` type): AWS access keys, GitHub tokens,
  OpenAI / Anthropic / Google / Slack / Stripe keys, JWTs, PEM private-key blocks, database
  connection URIs with embedded credentials, and a keyword-gated generic secret assignment.
- **Gateway streaming**: `stream=true` on `/v1/chat/completions` with placeholder-aware
  hold-back so a token split across chunks is never emitted half-restored.
- **Anthropic-compatible endpoint** `/v1/messages` (scrub -> OpenAI-compatible upstream ->
  restore, in the Anthropic request/response shape).
- Configurable spaCy NER labels (`ner_labels`); large-corpus eval mode
  (`scripts/eval.py --corpus ai4privacy`); a representation A/B experiment
  (`scripts/experiment_surrogate.py`).

### Fixed
- Gateway now restores PII inside tool-call / function-call arguments (previously only the
  string message content was restored).

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
