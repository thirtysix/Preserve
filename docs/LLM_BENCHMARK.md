# Layer 3 Local LLM Benchmark Results

## Overview

This benchmark evaluates small local LLM models for use as Preserve's Layer 3 PII reviewer. Layer 3 examines text regions that the normalcy scanner (Layer 1) flagged as suspicious but regex pattern matching (Layer 2) could not confidently classify. The LLM runs entirely locally; no data leaves the machine.

Two backends are supported:
- **Server** (recommended): Native llama-server via OpenAI-compatible HTTP API. Start with `./scripts/start_llm_server.sh [gpu|cpu]`.
- **Embedded**: llama-cpp-python in-process. No server needed, but ~20% slower on CPU.

The headline results below are from the current shipped pipeline on GPU. The detailed per-case tables further down come from an earlier CPU run whose ranking has been superseded (see the note under Summary Results).

## Models Tested

| Model | Quantization | File Size | RAM Required | Source |
|-------|-------------|-----------|-------------|--------|
| Qwen3.5-0.8B | Q4_K_M | 508 MB | ~3 GB | [unsloth/Qwen3.5-0.8B-GGUF](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF) |
| Qwen3.5-2B | Q4_K_M | 1.2 GB | ~3.5 GB | [unsloth/Qwen3.5-2B-GGUF](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF) |
| Qwen3.5-4B | Q4_K_M | 2.6 GB | ~5.5 GB | [unsloth/Qwen3.5-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) |

## Summary Results

Current pipeline, measured 2026-06-23: native `llama-server` with full GPU offload
(`-ngl 99`) on an RTX 3060 6 GB Laptop GPU, `--reasoning off`, selected-prompt mode,
the 16-case set. Reproduce with `python scripts/benchmark_llm.py --backend server`.

| Model | Precision | Recall | F1 Score | Avg Time/Region | Server Start |
|-------|-----------|--------|----------|-----------------|--------------|
| Qwen3.5-0.8B | 45.7% | 51.6% | 0.485 | 0.59s | 2.0s |
| Qwen3.5-2B | 71.4% | 32.3% | 0.444 | 0.49s | 2.0s |
| **Qwen3.5-4B** | **89.3%** | **80.6%** | **0.847** | 2.62s | 2.0s |

**Selected model**: Qwen3.5-4B Q4_K_M, by a wide margin: best F1 (0.85), best precision
(89%), best recall (81%). On GPU it stays fast (~2.6s/region); on CPU it is slower
(~24s/region), so the 0.8B/2B remain options for CPU-only or low-memory setups. The 0.8B
is fast but noisy, much of its apparent recall is spurious (it tagged words like "She",
"lives", and "at" as names), which is why its precision is only 46%.

### Superseded: 2026-03-30 CPU run

An earlier embedded-CPU benchmark (llama-cpp-python, pre-prompt-fix conditions: 4 few-shot
examples and `/no_think` inside a system prompt) ranked the 0.8B first. That ranking did
not survive a fair re-run on the current pipeline and is kept only for history:

| Model | Precision | Recall | F1 Score | Avg Time/Region |
|-------|-----------|--------|----------|-----------------|
| Qwen3.5-0.8B | 67.9% | 61.3% | 0.644 | 6.9s |
| Qwen3.5-2B | 66.7% | 38.7% | 0.490 | 10.3s |
| Qwen3.5-4B | 80.0% | 51.6% | 0.627 | 24.2s |

The reversal came mostly from cleaner thinking-mode handling (`--reasoning off` on the
native server) plus the selected-prompt architecture, which the larger model benefits from
most; the old CPU run also throttled the 4B to 24s/region. The per-case tables below detail
this superseded CPU run.

## Per-Case Results

### Qwen3.5-0.8B-Q4_K_M

| Test Case | Status | Expected | TP | FN | FP | Time |
|-----------|--------|----------|-----|-----|-----|------|
| bare_names_western | FAIL | 2 | 0 | 2 | 0 | 4.4s |
| bare_names_nordic | PARTIAL | 2 | 2 | 0 | 1 | 7.8s |
| bare_names_asian | PASS | 2 | 2 | 0 | 0 | 6.3s |
| bare_names_latin | FAIL | 2 | 0 | 2 | 0 | 4.7s |
| intl_address_italian | PASS | 1 | 1 | 0 | 0 | 5.2s |
| intl_address_finnish | FAIL | 1 | 0 | 1 | 0 | 5.4s |
| intl_address_mexican | FAIL | 1 | 0 | 1 | 0 | 5.6s |
| intl_address_german | FAIL | 1 | 0 | 1 | 0 | 5.6s |
| standalone_dates | FAIL | 3 | 0 | 3 | 0 | 6.5s |
| passport_numbers | PARTIAL | 2 | 1 | 1 | 0 | 5.6s |
| mixed_pii | **PASS** | 6 | 6 | 0 | 0 | 10.1s |
| no_pii_medical | PASS | 0 | 0 | 0 | 0 | 5.0s |
| no_pii_instructions | PASS | 0 | 0 | 0 | 0 | 5.8s |
| no_pii_technical | PASS | 0 | 0 | 0 | 0 | 5.7s |
| financial_data | PARTIAL | 2 | 2 | 0 | 3 | 13.3s |
| dataset_row_narrative | PARTIAL | 6 | 5 | 1 | 5 | 13.0s |

### Qwen3.5-2B-Q4_K_M

| Test Case | Status | Expected | TP | FN | FP | Time |
|-----------|--------|----------|-----|-----|-----|------|
| bare_names_western | FAIL | 2 | 0 | 2 | 0 | 8.8s |
| bare_names_nordic | FAIL | 2 | 0 | 2 | 0 | 7.9s |
| bare_names_asian | FAIL | 2 | 0 | 2 | 0 | 8.2s |
| bare_names_latin | FAIL | 2 | 0 | 2 | 0 | 10.8s |
| intl_address_italian | FAIL | 1 | 0 | 1 | 0 | 8.8s |
| intl_address_finnish | FAIL | 1 | 0 | 1 | 0 | 8.1s |
| intl_address_mexican | FAIL | 1 | 0 | 1 | 0 | 7.6s |
| intl_address_german | FAIL | 1 | 0 | 1 | 0 | 8.9s |
| standalone_dates | FAIL | 3 | 0 | 3 | 0 | 7.6s |
| passport_numbers | FAIL | 2 | 0 | 2 | 0 | 7.6s |
| mixed_pii | PARTIAL | 6 | 6 | 0 | 1 | 20.3s |
| no_pii_medical | PASS | 0 | 0 | 0 | 0 | 9.6s |
| no_pii_instructions | PASS | 0 | 0 | 0 | 0 | 7.9s |
| no_pii_technical | PASS | 0 | 0 | 0 | 0 | 8.0s |
| financial_data | FAIL | 2 | 0 | 2 | 0 | 8.6s |
| dataset_row_narrative | PARTIAL | 6 | 6 | 0 | 5 | 25.9s |

### Qwen3.5-4B-Q4_K_M

| Test Case | Status | Expected | TP | FN | FP | Time |
|-----------|--------|----------|-----|-----|-----|------|
| bare_names_western | FAIL | 2 | 0 | 2 | 0 | 18.0s |
| bare_names_nordic | FAIL | 2 | 0 | 2 | 0 | 17.9s |
| bare_names_asian | PASS | 2 | 2 | 0 | 0 | 24.9s |
| bare_names_latin | FAIL | 2 | 0 | 2 | 0 | 18.0s |
| intl_address_italian | FAIL | 1 | 0 | 1 | 0 | 17.5s |
| intl_address_finnish | FAIL | 1 | 0 | 1 | 0 | 20.7s |
| intl_address_mexican | FAIL | 1 | 0 | 1 | 0 | 18.7s |
| intl_address_german | FAIL | 1 | 0 | 1 | 0 | 17.6s |
| standalone_dates | FAIL | 3 | 0 | 3 | 0 | 19.3s |
| passport_numbers | PASS | 2 | 2 | 0 | 0 | 29.8s |
| mixed_pii | PARTIAL | 6 | 6 | 0 | 1 | 49.9s |
| no_pii_medical | PASS | 0 | 0 | 0 | 0 | 25.7s |
| no_pii_instructions | PASS | 0 | 0 | 0 | 0 | 20.8s |
| no_pii_technical | PASS | 0 | 0 | 0 | 0 | 18.0s |
| financial_data | FAIL | 2 | 0 | 2 | 0 | 18.9s |
| dataset_row_narrative | PARTIAL | 6 | 6 | 0 | 3 | 50.9s |

## Test Cases

16 test cases covering PII types that regex patterns struggle with:

| Category | Cases | Total Expected PII | Description |
|----------|-------|-------------------|-------------|
| Bare names | 4 | 8 | Western, Nordic, Asian, Latin American names without context keywords |
| International addresses | 4 | 4 | Italian, Finnish, Mexican, German street formats |
| Standalone dates | 1 | 3 | ISO and EU date formats without "DOB" prefix |
| Passport numbers | 1 | 2 | Bare alphanumeric strings without "passport" keyword |
| Mixed PII | 1 | 6 | Full patient record with names, DOB, address, passport, phone |
| No PII (negative) | 3 | 0 | Medical text, instructions, technical content |
| Financial data | 1 | 2 | IBAN, salary figures |
| Full dataset row | 1 | 6 | Narrative form of a test dataset row |

**Total**: 31 expected PII items + 3 negative cases.

## Key Findings

1. **The 4B model is the best overall choice** (current pipeline): highest F1 (0.847), precision (89.3%), and recall (80.6%). The earlier "0.8B is best" result was an artifact of the superseded CPU run; on a fair re-run the 0.8B's recall proved largely spurious (precision 46%) and bigger was clearly better, as expected.

2. **All models excel at mixed/contextual PII**: when text contains multiple PII types with surrounding context (the `mixed_pii` and `dataset_row_narrative` cases), all models detected 5-6 of 6 items. This is exactly what Layer 3 receives from the normalcy scanner.

3. **All models struggle with short, isolated fragments**: bare names, standalone addresses, and dates in isolation are hard for small models. This is acceptable because Layer 2 (regex) handles structured patterns, and Layer 3 only processes regions with surrounding context.

4. **False positives cluster around medical/geographic data**: all models occasionally flag disease names, country names, and blood types as PII. This can be mitigated by filtering detections against the normalcy scanner's safe-text patterns.

5. **Thinking mode must be disabled**: Qwen3.5 models enter `<think>` mode in completion prompts, consuming tokens on reasoning instead of outputting JSON. Using chat mode with `/no_think` in the system prompt resolves this, reducing 4B inference from ~80s to ~24s per region.

## Methodology

- Each model was loaded fresh, one at a time
- The same 16 test cases were run against each model in identical order
- Inference used `temperature=0.0` for deterministic output
- A detection counted as a true positive if the detected text substring overlapped with (contained or was contained by) the expected text
- Precision = TP / (TP + FP), Recall = TP / (TP + FN), F1 = 2 * P * R / (P + R)
- Benchmark script: `scripts/benchmark_llm.py`
- Full per-case results: [`tests/benchmark_results.tsv`](../tests/benchmark_results.tsv)

## Notes

- This benchmark tests Layer 3 in **isolation** (LLM only, no regex or normalcy scanner). The full three-layer pipeline combines regex pattern matching (Layer 2) with LLM review (Layer 3), where regex handles structured PII and the LLM catches contextual PII that regex misses. Combined performance is expected to be significantly higher.
- The per-model accuracy table above used CPU inference. GPU acceleration (native `llama-server`, `-ngl 99` full offload on an RTX 3060 6 GB Laptop GPU) was measured separately over the same 16-case set:

  | Model | CPU avg/case | GPU avg/case | GPU median | Speedup |
  |-------|-------------|-------------|-----------|---------|
  | Qwen3.5-0.8B | 6.87s | 0.56s | 0.19s | ~12× |
  | Qwen3.5-2B | 10.29s | 0.39s | 0.14s | ~26× |
  | Qwen3.5-4B | 24.17s | 1.74s | 0.86s | ~14× |

  All layers offloaded to GPU (0.8B/2B: 25/25, 4B: 33/33); VRAM use 1.2/2.0/3.6 GB respectively (all fit in 6 GB). Peak GPU temperature 82 °C during the 4B run, with no thermal throttling observed. Measured 2026-06-21.
- The Q4_K_M quantization was used for all models. Higher quantization (Q8_0) may improve accuracy at the cost of memory and speed.

## Backend Comparison (Qwen3.5-0.8B, same test case)

| Backend | Device | Avg Time | Notes |
|---------|--------|----------|-------|
| llama-cpp-python (embedded) | CPU 4 threads | 23.1s | Python bindings, in-process |
| llama-server (native) | CPU 4 threads | 18.5s | ~20% faster, native C++ HTTP server |
| llama-server (native) | GPU (RTX 3060 6GB) | 0.56s | 16-case mean (median 0.19s); confirms the sub-1s expectation |

The native llama-server backend is recommended for production use. It provides:
- ~20% faster inference than the Python bindings on CPU
- GPU support via `-ngl 99` (full offload)
- Built-in prompt caching across requests
- 4 parallel inference slots for concurrent requests
- OpenAI-compatible API (use the `openai` Python SDK)

### Important: Thinking mode

Qwen3.5 models have a "thinking" mode that generates `<think>...</think>` blocks before the actual response. This must be disabled:
- **llama-server**: Use `--reasoning off` flag
- **llama-cpp-python**: Use chat mode with NO system message (system prompt + `/no_think` causes 0.8B to return empty). Put instructions in user message only.
- **Completion mode without mitigation**: Generates 70-85s of thinking tokens, returns empty content

## Prompt Mode Comparison

Two prompt strategies were tested on 10 cases:

| Mode | Precision | Recall | F1 | Avg Time | Description |
|------|-----------|--------|-----|----------|-------------|
| **selected** | **100%** | **73.7%** | **0.848** | 9.9s | 1-2 examples matched to input PII types |
| comprehensive | 91.7% | 57.9% | 0.710 | 6.2s | Single dense example covering 7 types |

"Selected" mode is the default; it picks the most relevant examples from a bank of 6, producing better accuracy at a small speed cost.

### Prompt Architecture (current)
- No system message (critical for 0.8B Qwen3.5)
- Instructions + 1-2 selected examples + negative example + input, all in user message
- Suspicious regions marked with `>>>..<<<` delimiters, snapped to word boundaries
- Total prompt: ~1300 chars (~325 tokens)

## Full Pipeline Results (Messy Input)

When Layer 3 runs on the 10 hardest messy-input cases (informal text, no caps, abbreviations):

| Metric | Layer 2 Only | Layer 2 + LLM |
|--------|-------------|---------------|
| Detection rate | ~75% | **86.8%** |

Layer 3 caught items Layer 2 couldn't:
- "john smith" (both words too common for gazetteer)
- "4567" (bare card digits), "via roma" (address without number)
- "MEX-2345-6789" (custom ID format)
- "april 5th" (natural language date without year)

The LLM only fired on 4 of 10 cases, staying quiet when Layer 2 had things covered.
