# Preserve

Privacy-preserving PII detection and scrubbing for LLM inference queries. Preserve detects and removes personally identifiable information from your prompts **before they leave your machine**, then re-inserts the original values into responses locally.

- **Local-first:** detection runs on your machine; nothing is sent to scrub PII.
- **Reversible:** every redaction maps to a placeholder (`[NAME_1]`) and restores exactly.
- **International:** 60+ regex patterns and 9 checksum validators across 15+ countries, plus secrets (API keys, tokens).
- **Layered:** fast deterministic detection, with an optional local LLM for the hard cases.

[![PyPI](https://img.shields.io/pypi/v/preserve-pii.svg)](https://pypi.org/project/preserve-pii/)
[![CI](https://github.com/thirtysix/Preserve/actions/workflows/ci.yml/badge.svg)](https://github.com/thirtysix/Preserve/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-live-brightgreen)](https://thirtysix.github.io/Preserve/)

## Live Demo

A browser-based demo of the **deterministic** detection layer (regex + checksum validation) runs entirely client-side; no data leaves your browser:

**→ https://thirtysix.github.io/Preserve/** *(enabled when the repository is public)*

The demo also runs a compact build of the gazetteer name scorer, so it catches bare names across 55 countries. The Python package adds the full name scorer (the complete names-dataset) and the optional local LLM review described below.

## Workflows

A few common ways to put Preserve to work. In every case the raw PII stays on the local
machine; only placeholders ever travel to a third-party model.

### 1. Protect an existing chatbot or agent

Already calling an OpenAI-compatible endpoint? Route the call through `PreserveClient` and
the rest of your app is unchanged. PII is scrubbed before the request leaves, and the
model's answer comes back with the real values restored.

```python
from preserve import create_client, SensitivityLevel

client = create_client(
    api_key="your-deepinfra-or-openai-key",
    model="meta-llama/Llama-3.3-70B-Instruct",
    sensitivity_level=SensitivityLevel.STANDARD,
)

reply = client.chat([
    {"role": "system", "content": "You are a clinical scheduling assistant."},
    {"role": "user", "content": "Book a follow-up for Mikko Virtanen (HETU 131052-308T)."},
])
print(reply.text)   # the upstream model only ever saw [NAME_1] and [FINLAND_HETU_1]
```

### 2. Scrub here, infer anywhere (reversible hand-off)

When the model call happens somewhere you do not control (a hosted notebook, a colleague's
tool, a separate service), scrub first, carry the placeholder map alongside the sanitized
text, and restore the response when it comes back. The map serializes to plain JSON, so the
two halves can run in different processes or on different machines.

```python
import json
from preserve import Scrubber, PreserveConfig, PlaceholderMap

scrubber = Scrubber(PreserveConfig(use_name_scorer=True))

# 1. Scrub locally
result = scrubber.scrub("Email jane@acme.com the lab results for patient John Smith.")
sanitized = result.sanitized_text                        # "Email [EMAIL_1] the lab results for patient [NAME_1]."
map_json = json.dumps(result.placeholder_map.to_dict())  # store or transmit this safely

# 2. ... send `sanitized` to any model or tool; get back a response that reuses the placeholders ...
response = "Sent [EMAIL_1] the results and flagged [NAME_1] for follow-up."

# 3. Restore locally with the saved map
pm = PlaceholderMap.from_dict(json.loads(map_json))
print(scrubber.restore(response, pm))
# "Sent jane@acme.com the results and flagged John Smith for follow-up."
```

### 3. De-identify a dataset before analysis or sharing

Scrub a whole CSV column-aware (each column classified by its header name), or scrub records
in your own code. Useful for handing data to analysts, notebooks, or outside collaborators.

```bash
# Column-aware CSV scrub (writes a de-identified copy)
python -m preserve scrub-csv patients.csv -o patients.deid.csv
```

```python
from preserve.structured import StructuredScrubber

scrubber = StructuredScrubber()
record = {
    "full_name": "Aino Korhonen",
    "email": "aino@example.com",
    "notes": "called re HETU 150390A234B",
}
clean, pm = scrubber.scrub_dict(record)
# {'full_name': '[NAME_1]', 'email': '[EMAIL_1]', 'notes': 'called re [FINLAND_HETU_1]'}
```

### 4. PII pre-flight audit (no scrubbing)

Use detect-only to find leaks before they happen, for example as a pre-commit hook or CI
gate that blocks text/markdown/CSV files containing PII. `detect` emits JSON and reads stdin.

```bash
# Fail the step if any staged doc contains PII
for f in $(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(md|txt|csv)$'); do
  n=$(python -m preserve detect - -f json < "$f" | jq 'length')
  [ "$n" -gt 0 ] && { echo "PII detected in $f ($n items)"; exit 1; }
done
```

### 5. One gateway for a whole team

For many (often non-technical) users, run the [API gateway](#api-gateway-central-deployment)
below: everyone points their existing OpenAI client at one URL, PII never reaches the upstream
provider, and no per-user code changes are needed.

## Architecture

```
Input text
    │
Layer 1: NORMALCY SCANNER
    │   Scores text regions by how "normal" they look
    ▼
Layer 2: DETECTION PIPELINE
    ├── 2a: Regex (60+ patterns, 15+ countries, secrets)
    ├── 2b: Domain parsers (phonenumbers, email-validator, dateparser)
    ├── 2c: Checksum validation (Luhn, IBAN, HETU, DNI, CPF, BSN, NHS, RRN)
    ├── 2d: Context-aware confidence scoring
    ├── 2e: Allow-list filtering
    ├── 2f: Obfuscation normalization ("[at]"/"[dot]", spelled digits, homoglyphs)
    ├── 2g: Optional spaCy NER
    └── 2h: Hybrid name scorer (names-dataset + wordfreq gazetteer)
    │
Layer 3: LOCAL LLM REVIEW (optional)
    │   Qwen3.5 (4B default) via llama-server or llama-cpp-python
    │   Reviews suspicious regions with >>>..<<< markers
    │   Runs locally; nothing leaves the machine
    ▼
Output: sanitized text + reversible placeholder map
```

The browser demo implements **Layers 2a + 2c + 2d** (regex, checksums, context scoring) plus a compact build of the **2h** name gazetteer, so it catches both titled names ("Dr. Lee", "Patient: Aurora Rossi") and bare names across 55 countries ("Mikko Virtanen", "Hiroshi Tanaka"). Layers 2b/2g, the complete names-dataset, and Layer 3 require the Python package.

## Performance

### Detection rates

Measured **in context** (PII embedded in natural-language prompts, the realistic case).
Reproduce everything with `python scripts/eval.py` (full breakdown in
[`docs/EVALUATION.md`](docs/EVALUATION.md)); the LLM figures are from
[`docs/LLM_BENCHMARK.md`](docs/LLM_BENCHMARK.md).

| Dataset | Layer 2 only (recall / precision) | Layer 2 + LLM |
| --- | --- | --- |
| Clean data (100 rows, 1200 PII items) | **99.8%** / 99.9% | n/a (no headroom left) |
| Messy data (23 cases, 82 PII items) | **80.5% to 90.2%** / 84.6% to 90.2% | see hardest subset below |
| Hardest messy subset (10 cases) | ~75% | **86.8%** |

The messy figure is a range on purpose: the low end is a **strict** score (a partial or
boundary detection counts as a miss, since a partial redaction is a partial leak) and the
high end is an **overlap** score (any character overlap counts). Same detector, two
yardsticks, reported together so the number doesn't appear to drift. See `docs/EVALUATION.md`.

The LLM's job is the long tail, not the easy cases. On clean, well-structured data Layer 2
alone already reaches 99.8%, so the LLM has essentially nothing to add there (hence `n/a`).
Its value shows on the hardest messy cases, where it lifts recall from ~75% to 86.8% by
catching things deterministic rules miss: the bare name "john smith" (both words too common
for the gazetteer), "via roma" (an address with no number), the custom ID "MEX-2345-6789",
and "april 5th" (a natural-language date with no year). It stays quiet when Layer 2 already
has a region covered (it fired on only 4 of those 10 cases).

All 100 clean rows also round-trip exactly (scrub → restore reproduces the original).

### Per-column detection (clean data, in context, Layer 2)

| Column | Rate | Column | Rate |
| --- | --- | --- | --- |
| full_name | 100% | credit_card | 100% |
| date_of_birth | 100% | ip_address | 100% |
| email | 100% | address | 98% |
| phone | 100% | emergency_contact_name | 100% |
| national_id | 100% | emergency_contact_phone | 100% |
| passport_number | 100% | bank_account | 100% |

> Detection rates are highest in context. Several patterns (passport, address, names)
> intentionally require a nearby keyword, so a bare value scrubbed *with no surrounding
> text* scores lower; the test script reports that isolated-value lower bound too.

### Layer 3 inference speed

Layer 3 model comparison over the 16-case benchmark set (Qwen3.5, Q4_K_M). GPU figures use the native `llama-server` with `-ngl 99` full offload on an RTX 3060 6 GB Laptop GPU (measured 2026-06-21):

| Model | VRAM | CPU avg/case | GPU avg/case | Speedup |
| --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | 1.2 GB | 6.87s | **0.56s** | ~12× |
| Qwen3.5-2B | 2.0 GB | 10.29s | **0.39s** | ~26× |
| Qwen3.5-4B | 3.6 GB | 24.17s | **1.74s** | ~14× |

All three models fit comfortably in 6 GB VRAM. Full methodology in [`docs/LLM_BENCHMARK.md`](docs/LLM_BENCHMARK.md).

## Quick Start

```bash
pip install preserve-pii          # the import name is `preserve`
# extras: preserve-pii[llm]  (local LLM)  ·  [api]  (gateway)  ·  [ner]  ·  [all]
```

Or from source for development:

```bash
git clone https://github.com/thirtysix/Preserve && cd Preserve
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # Add your DEEPINFRA_API_KEY
```

```python
from preserve import create_client, SensitivityLevel

client = create_client(
    api_key="your-api-key",
    model="meta-llama/Llama-3.3-70B-Instruct",
    sensitivity_level=SensitivityLevel.STANDARD,
)

response = client.chat([
    {"role": "user", "content": "Patient John Smith (john@hospital.com, SSN 123-45-6789) needs a follow-up plan."}
])

print(response.text)  # PII scrubbed before sending, restored in response
```

## Scrub and Restore

Every redaction is reversible. `scrub()` returns a `placeholder_map` that maps each
placeholder back to its original value, so you can restore the real data locally: either
the original text or, more usefully, a model's **response** that still contains placeholders.

```python
from preserve import Scrubber, PreserveConfig, SensitivityLevel

config = PreserveConfig(
    sensitivity_level=SensitivityLevel.AGGRESSIVE,
    use_name_scorer=True,      # Hybrid name detection (names-dataset + wordfreq)
)
scrubber = Scrubber(config)

result = scrubber.scrub("Patient aurora rossi, SSN 123-45-6789, at Via Roma 31")

print(result.sanitized_text)        # "Patient [NAME_1], SSN [SSN_1], at [ADDRESS_1]"
print(result.pii_summary)           # {'NAME': 1, 'SSN': 1, 'ADDRESS': 1}

# Inspect the reversible mapping (placeholder -> original value)
print(result.placeholder_map.entries())
# {'[NAME_1]': 'aurora rossi', '[SSN_1]': '123-45-6789', '[ADDRESS_1]': 'Via Roma 31'}

# Restore the original text exactly
restored = scrubber.restore(result.sanitized_text, result.placeholder_map)
assert restored == result.original_text

# In practice you send `sanitized_text` to the LLM and restore its *response*,
# which comes back referencing the same placeholders:
model_response = "Schedule a follow-up for [NAME_1]; verify [SSN_1] on file."
print(scrubber.restore(model_response, result.placeholder_map))
# "Schedule a follow-up for aurora rossi; verify 123-45-6789 on file."
```

The mapping also serializes (`placeholder_map.to_dict()` / `PlaceholderMap.from_dict(...)`),
so the scrub and restore steps can happen in different processes, which is useful for the API setup below.

## API Gateway (central deployment)

For teams where many (possibly non-technical) people make LLM calls, run Preserve as a
**central gateway**: an OpenAI-compatible proxy that scrubs PII before forwarding to the
upstream model and restores it in the response. Users point their existing OpenAI SDK at the
gateway, with no other code changes.

> **Trust model:** in this mode PII leaves the user's machine but stays **inside your
> organization**: it never reaches the third-party LLM provider (OpenAI/Anthropic/DeepInfra).
> The placeholder map lives only for the duration of a request and is never persisted; audit
> logs record detection *counts*, never values. (If you need PII to never leave the device at
> all, scrub client-side with the library instead.)

```bash
# Configure and run (see preserve/api/settings.py for all options)
export PRESERVE_UPSTREAM_API_KEY=...   # org's upstream key (users never see it)
export PRESERVE_API_KEYS='{"sk-team-alpha":{"name":"alpha","rpm":60,"daily_token_quota":2000000}}'
./scripts/run_api.sh                   # serves on http://127.0.0.1:8800 (Swagger UI at /docs)
```

```python
# Any OpenAI client works; just change base_url and use a gateway key:
from openai import OpenAI
client = OpenAI(base_url="http://your-server:8800/v1", api_key="sk-team-alpha")

resp = client.chat.completions.create(
    model="meta-llama/Llama-3.3-70B-Instruct",
    messages=[{"role": "user", "content": "Email a summary to jane@acme.com about patient John Smith."}],
)
print(resp.choices[0].message.content)   # PII restored; the upstream model only ever saw placeholders
```

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/chat/completions` | OpenAI-compatible proxy: scrub → upstream LLM → restore (supports `stream=true`). Map never stored. |
| `POST /v1/messages` | Anthropic-compatible proxy (same scrub → upstream → restore, Anthropic request/response shape). |
| `POST /v1/scrub` | Scrub only → returns sanitized text + a reversible placeholder map (client holds it). |
| `POST /v1/restore` | Re-insert PII given text + that map. |
| `POST /v1/detect` | Detection only (types/spans/confidence); `include_values: false` omits raw PII. |
| `GET /health` | Liveness. |

Built in: per-key API-key auth (`Authorization: Bearer …`), per-key requests/min + daily token
quotas, input-size caps, and PII-free audit logging (`logs/api_audit.jsonl`). Rate limiting is
in-memory by default and uses **Redis** automatically when `REDIS_URL` is set (multi-worker/host).

**Production deploy** (Docker Compose + Redis, TLS, systemd, shared-host), see
[`docs/DEPLOY.md`](docs/DEPLOY.md):

```bash
cp .env.example .env   # set PRESERVE_UPSTREAM_API_KEY + PRESERVE_API_KEYS
docker compose up --build -d   # API on 127.0.0.1:8800 + Redis; put TLS proxy in front
```

## PII and Secret Coverage (60+ patterns)

| Region | Identifiers |
| --- | --- |
| US | SSN, ITIN, email, passport, credit card, phone, IPv4/IPv6, DOB, address, ZIP, MRN, DEA, NPI, EIN, driver's license, insurance ID |
| UK | NINO, NHS number, phone |
| Finland | HETU, Y-tunnus, veronumero, phone, addresses (-katu, -tie) |
| Canada | SIN, provincial health cards |
| France | NIR/INSEE, phone |
| Germany | Personalausweis, Steuer-ID, addresses (-straße, -weg) |
| Brazil | CPF, CNPJ |
| India | Aadhaar, PAN |
| Mexico | CURP, RFC |
| Spain | DNI, NIE |
| Italy | Codice Fiscale, addresses (Via, Corso, Piazza) |
| South Korea | RRN |
| Japan | My Number |
| Netherlands | BSN, addresses (-gracht, -straat) |
| Banking | IBAN, SWIFT/BIC, context-based account numbers |
| Secrets | API keys (AWS, GitHub, OpenAI, Anthropic, Google, Slack, Stripe), JWTs, PEM private keys, DB connection strings |
| Names | Hybrid scorer (gazetteer + word frequency + context), handles lowercase and 15+ countries |

## Messy Input Handling

Preserve handles real-world text, not just clean data:

- No capitalization ("aurora rossi" detected via gazetteer)
- Abbreviations ("pt", "dob", "ssn", "addr")
- Typos ("Aurrora Rossi" still caught)
- Mixed languages ("Asiakas Mikko Virtanen soitti eilen, his English is good")
- Copy-paste artifacts (tabs, line breaks)
- Obfuscation ("[at]", "[dot]", Unicode homoglyphs)
- Title/context keywords ("mrs korhonen", "wife maria", "pt J. Smith")

## Layer 3: Local LLM (Optional)

For PII that regex can't catch (bare names in informal text, natural-language dates, custom ID formats):

```bash
# Download a bundled Qwen3.5 GGUF (helper supports presets 0.8B / 2B / 4B):
python scripts/download_model.py --model 4B --quant Q4_K_M     # Qwen3.5-4B, recommended (best accuracy), ~2.6 GB
# python scripts/download_model.py --model 2B --quant Q4_K_M    # Qwen3.5-2B,  ~1.4 GB
# python scripts/download_model.py --model 0.8B --quant Q4_K_M  # Qwen3.5-0.8B, lightest/fastest on CPU, ~533 MB
# python scripts/download_model.py --list                       # show all preset size/quant combos
```

```python
# Option A: Server backend (fastest, GPU-capable)
config = PreserveConfig(use_llm_review=True, llm_backend="server")   # start the server first (below)

# Option B: Embedded backend (no server needed, CPU only)
config = PreserveConfig(use_llm_review=True, llm_backend="embedded",
                        llm_model_path="models/Qwen3.5-4B-Q4_K_M.gguf")
```

```bash
# Start the native server (used by backend="server"):
./scripts/start_llm_server.sh gpu   # or: cpu
```

### Using a different model

Preserve works with **any GGUF model**; the Qwen3.5 presets are just convenient defaults.
To use another model (e.g. from Hugging Face), download the `.gguf` and point Preserve at it
by its full path. For example, with a Llama or Mistral GGUF:

```bash
# Download any GGUF (repo + filename are the model's full names on Hugging Face):
huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \
    Llama-3.2-3B-Instruct-Q4_K_M.gguf --local-dir models/
```

```python
# Embedded backend, just set the path:
config = PreserveConfig(use_llm_review=True, llm_backend="embedded",
                        llm_model_path="models/Llama-3.2-3B-Instruct-Q4_K_M.gguf")
```

```bash
# Server backend: launch llama-server on that file, then use llm_backend="server":
vendor/llama.cpp/build/bin/llama-server -m models/Llama-3.2-3B-Instruct-Q4_K_M.gguf \
    -ngl 99 --reasoning off --host 127.0.0.1 --port 8090
```

> Larger models detect more but run slower; see the [inference table](#layer-3-inference-speed).
> GPU inference requires the native `llama-server` (built with CUDA). The embedded
> `llama-cpp-python` backend is CPU-only. Instruction-tuned models with a "thinking" mode
> (like Qwen3.5) must have it disabled; Preserve does this automatically. See
> [`docs/LLM_BENCHMARK.md`](docs/LLM_BENCHMARK.md).

## Configuration

```python
from preserve import PreserveConfig, SensitivityLevel

config = PreserveConfig(
    sensitivity_level=SensitivityLevel.AGGRESSIVE,
    use_name_scorer=True,        # Hybrid name detection (Layer 2h)
    use_normalcy_scanner=True,   # Layer 1
    use_ner=False,               # Layer 2g: spaCy NER (needs the `ner` extra)
    use_llm_review=False,        # Layer 3 (enable if needed)
    llm_backend="server",        # "server" or "embedded"
    use_allowlist=True,          # Filter known false positives
    known_names=["John Doe"],    # Always-detect list
    log_scrubbed_content=False,
)
```

### Recall vs. precision: spaCy NER (Layer 2g)

If you care more about catching everything than about over-redacting (often the
right trade-off for PII), enable NER:

```bash
pip install "preserve-pii[ner]"
python -m spacy download en_core_web_sm
```

```python
config = PreserveConfig(sensitivity_level=SensitivityLevel.AGGRESSIVE, use_ner=True)
```

On a 500-sample slice of the ai4privacy corpus, NER lifts recall from **66.8% to
82.8%** (+16 points) for only ~1 point of precision (89.7% to 88.5%), and is the best
config by F1. By default NER accepts `PERSON`, `GPE`, `FAC`, and `DATE`; `ORG` is
deliberately excluded because it drops precision ~8 points with little PII value (add
it via `ner_labels=[..., "ORG"]` only if you want maximum recall). Full numbers in
[`docs/CORPUS_EVAL.md`](docs/CORPUS_EVAL.md).

## Dashboards

**Browser demo (static, deterministic only):** open `docs/index.html` locally, or visit the [live demo](https://thirtysix.github.io/Preserve/) once the repo is public. Runs regex + checksum detection and a compact name gazetteer (55 countries) 100% client-side.

**Full Gradio app (all layers):**

```bash
source .venv/bin/activate
python dashboard.py
# Open http://127.0.0.1:7860
```

Three tabs:

- **Scrub:** input/output panels with 12 preloaded examples (clean, messy, multilingual, safe text). Toggle Layer 1/2/3 and sensitivity. Per-item detection table.
- **CSV Scrub:** upload a CSV for structured scrubbing with automatic column classification.
- **Compare:** run the same text through two configurations side by side.

## CLI

```bash
source .venv/bin/activate

python -m preserve scrub "Patient Aurora Rossi, SSN 123-45-6789"
python -m preserve detect "Patient Aurora Rossi" -f json
echo "text with PII" | python -m preserve scrub -
python -m preserve scrub-file input.txt -o output.txt
python -m preserve scrub-csv data.csv -o scrubbed.csv
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v              # 87 unit tests (detection, false positives, Layer 3 gate, API gateway)
python tests/test_against_dataset.py    # Per-column rates: isolated lower-bound + in-context (99.8%)
```

## Project Structure

```
preserve/              # Core library
  config.py            # Configuration
  patterns.py          # 60+ regex patterns (15+ countries + secrets)
  detectors.py         # Three-layer detection engine
  name_scorer.py       # Hybrid name detection (names-dataset + wordfreq)
  domain_parsers.py    # phonenumbers, email-validator, dateparser
  validators.py        # Checksum validation (Luhn, IBAN, etc.)
  context.py           # Context-aware confidence scoring
  allowlist.py         # False positive filtering
  obfuscation.py       # Obfuscation normalization
  normalcy.py          # Layer 1 normalcy scanner
  llm_review.py        # Layer 3 local LLM review
  structured.py        # Structured data mode (CSV/dict column-aware scrubbing)
  mapping.py           # Reversible placeholder mapping
  scrubber.py          # Scrub/restore pipeline
  client.py            # OpenAI-compatible API wrapper
  api/                 # FastAPI gateway (proxy, scrub/restore/detect, auth, quotas)
  __main__.py          # CLI interface (python -m preserve)

docs/                  # Research + static browser demo
  index.html           # Static demo (GitHub Pages entry point)
  assets/              # Demo JS/CSS + exported patterns
  PRIVACY_TAXONOMY.md  # Threat model and framework
  LLM_BENCHMARK.md     # Layer 3 model comparison (incl. GPU benchmarks)
  DEPLOY.md            # API gateway production deployment (Docker, TLS, Redis)

scripts/               # Utilities (server, model download, benchmarks, pattern + name-gazetteer export)
poc/                   # Proof-of-concept demos
tests/                 # 87 unit tests + benchmarks
dashboard.py           # Gradio web dashboard (all layers)
```

## Limitations

- **Single common-word names** ("Kim", "Grace" alone) may not be detected without context.
- **Deliberately redacted data** ("SSN ending in 6789") is partially detected.
- **Streaming** is supported on the gateway (`stream=true`): placeholders are restored
  incrementally with hold-back buffering so a token split across chunks is never emitted
  half-restored. Token-based quota accounting requires the client to request usage
  (`stream_options={"include_usage": true}`).
- **Browser demo** covers the deterministic layers (regex, checksums, context scoring) and a compact name gazetteer that catches bare names across 55 countries; the complete names-dataset and the local LLM (for the hardest cases) need the Python package.

## License

[MIT](LICENSE) © 2026 Harlan Barker
