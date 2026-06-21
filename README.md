# Preserve

Privacy-preserving PII detection and scrubbing for LLM inference queries. Automatically detects and removes personally identifiable information from your prompts before they leave your machine, then re-inserts the original values into responses locally.

## Architecture

```
Input text
    │
Layer 1: NORMALCY SCANNER
    │   Scores text regions by how "normal" they look
    ▼
Layer 2: DETECTION PIPELINE
    ├── 2a: Regex (49+ patterns, 13+ countries)
    ├── 2b: Domain parsers (phonenumbers, email-validator, dateparser)
    ├── 2c: Checksum validation (Luhn, IBAN, HETU, DNI, CPF, BSN, NHS, RRN)
    ├── 2d: Context-aware confidence scoring
    ├── 2e: Allow-list filtering
    ├── 2f: Obfuscation normalization ("[at]"/"[dot]", spelled digits, homoglyphs)
    ├── 2g: Optional spaCy NER
    └── 2h: Hybrid name scorer (names-dataset + wordfreq gazetteer)
    │
Layer 3: LOCAL LLM REVIEW (optional)
    │   Qwen3.5-0.8B via llama-server or llama-cpp-python
    │   Reviews suspicious regions with >>>..<<< markers
    │   Runs locally — nothing leaves the machine
    ▼
Output: sanitized text + reversible placeholder map
```

## Detection Rates

| Dataset | Layer 2 Only | Layer 2 + LLM |
|---------|-------------|---------------|
| **Clean data** (100 rows, 1200 PII items) | **99.8%** | — |
| **Messy data** (23 cases, 82 PII items) | **87.8%** | **~87%** on hardest subset |

### Per-Column (Clean Data, Layer 2)

| Column | Rate |
|--------|------|
| full_name | 99% |
| date_of_birth | 100% |
| email | 100% |
| phone | 100% |
| national_id | 100% |
| passport_number | 100% |
| bank_account | 100% |
| credit_card | 100% |
| ip_address | 100% |
| address | 99% |
| emergency_contact_name | 98% |
| emergency_contact_phone | 100% |

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
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

## Scrub Without Sending

```python
from preserve import Scrubber, PreserveConfig, SensitivityLevel

config = PreserveConfig(
    sensitivity_level=SensitivityLevel.AGGRESSIVE,
    use_name_scorer=True,      # Hybrid name detection (names-dataset + wordfreq)
)
scrubber = Scrubber(config)

result = scrubber.scrub("Patient aurora rossi, SSN 123-45-6789, at Via Roma 31")
print(result.sanitized_text)   # "Patient [NAME_1], SSN [SSN_1], at [ADDRESS_1]"
print(result.pii_summary)      # {'NAME': 1, 'SSN': 1, 'ADDRESS': 1}

# Restore
restored = scrubber.restore(result.sanitized_text, result.placeholder_map)
assert restored == result.original_text
```

## International PII Coverage (49+ patterns)

| Region | Identifiers |
|--------|-------------|
| **US** | SSN, ITIN, email, passport, credit card, phone, IP, DOB, address, ZIP, MRN, DEA, NPI, EIN, driver's license, insurance ID |
| **UK** | NINO, NHS number, phone |
| **Finland** | HETU, Y-tunnus, veronumero, phone, addresses (-katu, -tie) |
| **Canada** | SIN, provincial health cards |
| **France** | NIR/INSEE, phone |
| **Germany** | Personalausweis, Steuer-ID, addresses (-straße, -weg) |
| **Brazil** | CPF, CNPJ |
| **India** | Aadhaar, PAN |
| **Mexico** | CURP, RFC |
| **Spain** | DNI, NIE |
| **Italy** | Codice Fiscale, addresses (Via, Corso, Piazza) |
| **South Korea** | RRN |
| **Japan** | My Number |
| **Netherlands** | BSN, addresses (-gracht, -straat) |
| **Banking** | IBAN, SWIFT/BIC, context-based account numbers |
| **Names** | Hybrid scorer (gazetteer + word frequency + context), handles lowercase and 15+ countries |

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

For PII that regex can't catch (bare names in informal text, natural language dates, custom ID formats):

```bash
# Download model (508 MB)
python scripts/download_model.py --model 0.8B --quant Q4_K_M

# Option A: Server backend (fastest)
./scripts/start_llm_server.sh cpu   # or: gpu
# Then in Python:
config = PreserveConfig(use_llm_review=True, llm_backend="server")

# Option B: Embedded backend (no server needed)
config = PreserveConfig(use_llm_review=True, llm_backend="embedded")
```

## Configuration

```python
from preserve import PreserveConfig, SensitivityLevel

config = PreserveConfig(
    sensitivity_level=SensitivityLevel.AGGRESSIVE,
    use_name_scorer=True,        # Hybrid name detection
    use_normalcy_scanner=True,   # Layer 1
    use_llm_review=False,        # Layer 3 (enable if needed)
    llm_backend="server",        # "server" or "embedded"
    use_allowlist=True,          # Filter known false positives
    known_names=["John Doe"],    # Always-detect list
    log_scrubbed_content=False,
)
```

## Project Structure

```
preserve/              # Core library
  config.py            # Configuration
  patterns.py          # 49+ regex patterns (13+ countries)
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
  audit.py             # Audit logging (JSON/CSV)
  client.py            # OpenAI-compatible API wrapper
  __main__.py          # CLI interface (python -m preserve)

docs/                  # Research and analysis
  PRIVACY_TAXONOMY.md  # Threat model and framework
  DEEPINFRA_ANALYSIS.md # DeepInfra privacy assessment
  PROVIDER_COMPARISON.md # Provider scoring rubric
  LLM_BENCHMARK.md     # Layer 3 model comparison

scripts/               # Utilities
  start_llm_server.sh  # Launch llama-server (GPU/CPU)
  download_model.py    # Download GGUF models
  benchmark_llm.py     # Layer 3 standalone benchmark
  benchmark_full_pipeline.py # Full pipeline benchmark
  test_prompt_modes.py # LLM prompt comparison

poc/                   # Proof of concept demos
  demo_basic.py        # End-to-end scrub/query/restore
  demo_comparison.py   # With vs without scrubbing
  demo_network_audit.py # Verify outgoing network traffic

tests/                 # 73 unit tests + benchmarks
  test_data.csv        # 100 rows, 29 columns, 15 countries
  messy_test_data.json # 23 messy/real-world test cases
  test_false_positives.py # 21 precision validation tests

dashboard.py           # Gradio web dashboard

vendor/                # Built from source (not in git)
  llama.cpp/           # Native llama-server

models/                # GGUF model files (not in git)
```

## Dashboard

Interactive web UI for testing and exploring PII detection:

```bash
source .venv/bin/activate
python dashboard.py
# Open http://127.0.0.1:7860
```

Three tabs:
- **Scrub** — Left/right input/output panels with 12 preloaded examples (clean, messy, multilingual, safe text). Toggle Layer 1/2/3 and sensitivity. Detection table with type, layer, and confidence per item.
- **CSV Scrub** — Upload a CSV file for structured scrubbing. Automatic column classification (e.g., "patient_name" → NAME). Shows which columns are PII.
- **Compare** — Run the same text through two different configurations side by side. See what each config catches.

## CLI

```bash
source .venv/bin/activate

# Scrub text
python -m preserve scrub "Patient Aurora Rossi, SSN 123-45-6789"

# Detect PII (JSON or table output)
python -m preserve detect "Patient Aurora Rossi" -f json

# Scrub from stdin
echo "text with PII" | python -m preserve scrub -

# Scrub a file
python -m preserve scrub-file input.txt -o output.txt

# Scrub a CSV (column-aware)
python -m preserve scrub-csv data.csv -o scrubbed.csv
```

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v              # 73 unit tests (including false positive tests)
python tests/test_against_dataset.py    # Per-column detection rates
```

## Limitations

- **Single common-word names** ("Kim", "Grace" alone) may not be detected without context
- **Deliberately redacted data** ("SSN ending in 6789") is partially detected
- **Streaming** responses not yet supported
- **GPU inference** throttles on laptops due to thermals
