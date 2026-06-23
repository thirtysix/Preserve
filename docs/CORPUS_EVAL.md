# Large-corpus evaluation (ai4privacy)

Beyond the small bundled sets, the eval harness can run against a large external
corpus: [`ai4privacy/pii-masking-200k`](https://huggingface.co/datasets/ai4privacy/pii-masking-200k)
(~209k labeled examples, multilingual). It is opt-in so the default fast eval needs no download.

```bash
pip install "preserve-pii[dev]"          # pulls the `datasets` library
python scripts/eval.py --corpus ai4privacy --n 1000        # English sample, config comparison
python scripts/eval.py --corpus ai4privacy --n 1000 --all-langs
python scripts/eval.py --corpus ai4privacy --n 200 --with-llm   # also run the local LLM config
```

The corpus uses a much larger PII taxonomy than Preserve targets. We map its labels to
Preserve's categories (FIRSTNAME/LASTNAME/MIDDLENAME to NAME, STREET/BUILDINGNUMBER/ZIPCODE
to ADDRESS, etc.). Gold entities of an **unsupported** type (JOBAREA, USERNAME, GENDER,
PASSWORD, URL, crypto addresses, ...) are out of scope: excluded from recall and never
counted as a false positive. Scoring is character-span overlap.

## Snapshot: 500 English samples, 692 in-scope entities (Layer 2, 2026-06-23)

| Config | Recall | Precision | F1 | F2 |
| --- | --- | --- | --- | --- |
| minimal | 46.5% | 91.7% | 0.617 | 0.516 |
| standard | 58.5% | 88.8% | 0.706 | 0.628 |
| aggressive | 66.8% | 89.5% | 0.765 | 0.703 |
| aggressive, no name-scorer | 49.6% | 92.0% | 0.644 | 0.546 |
| aggressive + NER (spaCy) | **85.8%** | 81.5% | **0.836** | **0.849** |

Per-category recall (aggressive):

| Category | Recall | Found/Total |
| --- | --- | --- |
| CREDIT_CARD | 100.0% | 27/27 |
| EMAIL | 100.0% | 47/47 |
| IBAN | 100.0% | 14/14 |
| PHONE | 89.7% | 26/29 |
| SSN | 87.5% | 14/16 |
| DATE | 72.4% | 55/76 |
| NAME | 61.3% | 146/238 |
| ADDRESS | 56.0% | 70/125 |
| ACCOUNT | 54.5% | 18/33 |
| IP | 51.7% | 45/87 |

## Takeaways

- **The gazetteer name scorer (Layer 2h) adds about 17 points of recall** (aggressive 66.8%
  vs 49.6% with it disabled).
- **spaCy NER is a strong recall lever on real-distribution text**: +19 points (66.8% to
  85.8%) and the best F1/F2, at a precision cost. It is off by default; enable
  `use_ner=True` when recall matters more than over-redaction.
- Headline recall is lower than the 99.8% on the bundled clean set because this corpus is
  harder and less keyword-rich. That is the point of an external corpus: a more honest,
  harder test.
- Weakest categories to improve: IP (IPv6), ADDRESS, ACCOUNT, NAME. These are also where the
  optional Layer 3 LLM helps most.
