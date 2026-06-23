"""Layer 2g spaCy NER tests. Skipped unless spaCy + the model are installed
(the `ner` extra), so CI without that extra is unaffected."""

import pytest

spacy = pytest.importorskip("spacy")

from preserve import Scrubber, PreserveConfig, SensitivityLevel


def _model_available() -> bool:
    try:
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _model_available(), reason="spaCy model en_core_web_sm not installed"
)


def _ner_dets(text, **cfg_kwargs):
    config = PreserveConfig(
        sensitivity_level=SensitivityLevel.AGGRESSIVE,
        use_name_scorer=False,  # isolate NER's contribution
        use_ner=True,
        **cfg_kwargs,
    )
    result = Scrubber(config).scrub(text)
    return [d for d in result.detections if d.detection_layer == "ner"]


def test_ner_detects_person():
    dets = _ner_dets("The report was reviewed by Barack Obama yesterday.", ner_labels=["PERSON"])
    assert any("Obama" in d.matched_text for d in dets)


def test_ner_labels_exclude_org_when_not_requested():
    # PERSON-only must not emit an ORG detection for a company name.
    dets = _ner_dets("Microsoft Corporation released a report.", ner_labels=["PERSON"])
    assert all(d.replacement_type != "ORG" for d in dets)


def test_default_ner_labels_exclude_org():
    # The default label set deliberately omits ORG.
    assert "ORG" not in PreserveConfig().ner_labels
    assert "PERSON" in PreserveConfig().ner_labels
