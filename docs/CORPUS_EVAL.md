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
| standard | 64.6% | 89.6% | 0.751 | 0.684 |
| aggressive | 72.8% | 90.2% | 0.806 | 0.757 |
| aggressive, no name-scorer | 55.6% | 92.7% | 0.695 | 0.605 |
| aggressive + NER (spaCy, default labels) | **87.6%** | 89.0% | **0.883** | **0.878** |

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
| IP | 100.0% | 87/87 |
| ADDRESS | 56.0% | 70/125 |
| ACCOUNT | 54.5% | 18/33 |

## NER label tuning (n=400)

spaCy NER's value depends heavily on which entity labels you accept. Sweeping the label set
(`ner_labels`) shows `ORG` is the precision killer, while `PERSON` is a free win:

| NER labels | Recall | Precision | F1 | F2 |
| --- | --- | --- | --- | --- |
| none (baseline) | 67.6% | 89.7% | 0.771 | 0.711 |
| PERSON | 75.2% | 89.8% | 0.819 | 0.777 |
| PERSON + GPE + FAC + DATE (default) | **82.8%** | 88.5% | **0.856** | 0.839 |
| all (+ ORG) | 86.2% | 81.1% | 0.836 | 0.851 |

So the default `ner_labels = ["PERSON", "GPE", "FAC", "DATE"]` captures almost all of NER's
recall gain at near-baseline precision; adding `ORG` buys ~3 more points of recall but costs
~8 points of precision and lowers F1, so it is excluded by default.

## NER on real data (TAB court cases, 400 docs)

The structural recall lever for locations/addresses is spaCy NER: regex can detect a
street + number, but it cannot recognize a bare city ("Warsaw", "Ankara") the way
NER's GPE/FAC entities can. Measured on real ECHR cases:

| Category | Regex only | + NER (`use_ner=True`) |
| --- | --- | --- |
| ADDRESS (mostly cities here) | 19% | **82%** |
| NAME | 66% | **90%** |
| DATE | 87% | **99%** |

NER roughly quadruples address recall on real prose. The cost is more over-redaction
(detections overlapping no gold span rose ~2.4x), which for anonymization is the
acceptable direction; it stays off by default because spaCy is an optional dependency.
This is why a dedicated address parser (e.g. libpostal) is not needed: NER already
reaches 82% on real text, and it covers names and dates too.

## Takeaways

- **Adding IPv6 detection took IP recall from 51.7% to 100%** and lifted overall aggressive
  recall about 6 points (66.8% to 72.8%). A concrete, corpus-driven fix.
- **The gazetteer name scorer (Layer 2h) adds about 17 points of recall** (aggressive 72.8%
  vs 55.6% with it disabled).
- **spaCy NER (tuned) is a strong, cheap recall lever on real-distribution text**: +15 points
  (72.8% to 87.6%) for ~1 point of precision, and the best config by F1. It is off by default
  (spaCy is an optional extra); enable `use_ner=True` when recall matters more than
  over-redaction.
- Headline recall is lower than the 99.8% on the bundled clean set because this corpus is
  harder and less keyword-rich. That is the point of an external corpus: a more honest,
  harder test.
- Weakest categories to improve next: ADDRESS, ACCOUNT, NAME. These are also where the
  optional Layer 3 LLM helps most.
