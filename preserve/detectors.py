"""
Three-layer PII detection engine with enhanced sublayers.

Layer 1:  Normalcy scanning — scores text regions by how 'normal' they look.
Layer 2:  Detection pipeline
  2a: Regex pattern matching (49+ patterns, 13+ countries)
  2b: Domain parsers (phonenumbers, email-validator, dateparser)
  2c: Checksum validation (Luhn, IBAN mod-97, etc.)
  2d: Context-aware confidence scoring
  2e: Allow-list filtering
  2f: Obfuscation normalization
  2g: Optional spaCy NER
Layer 3:  Local LLM review of uncertain regions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from preserve.config import PreserveConfig, SensitivityLevel
from preserve.patterns import PIIPattern, get_active_patterns


@dataclass
class PIIMatch:
    """A detected PII span in text."""

    start: int
    end: int
    matched_text: str
    pattern_name: str
    replacement_type: str
    sensitivity: SensitivityLevel
    detection_layer: str = "pattern"
    confidence: float = 1.0


class PIIDetector:
    """Enhanced three-layer PII detector."""

    def __init__(self, config: PreserveConfig) -> None:
        self.config = config
        self._patterns = get_active_patterns(config.sensitivity_level)
        self._ner_model = None
        self._normalcy_scanner = None
        self._llm_reviewer = None
        self._domain_parsers = None
        self._allowlist = None

        # Build known-names pattern if provided
        self._known_names_pattern: re.Pattern | None = None
        if config.known_names:
            escaped = [re.escape(name) for name in config.known_names]
            self._known_names_pattern = re.compile(
                r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE
            )

        # Build custom patterns
        self._custom_patterns: list[PIIPattern] = []
        for cp in config.custom_patterns:
            self._custom_patterns.append(
                PIIPattern(
                    name=cp["name"],
                    regex=re.compile(cp["regex"]),
                    min_sensitivity=SensitivityLevel.MINIMAL,
                    description=f"Custom pattern: {cp['name']}",
                    replacement_type=cp.get("replacement_type", cp["name"].upper()),
                )
            )

        # Layer 1: Normalcy scanner
        if config.use_normalcy_scanner:
            from preserve.normalcy import NormalcyScanner
            self._normalcy_scanner = NormalcyScanner(
                custom_safe_patterns=config.custom_safe_patterns or None,
            )

        # Layer 2b: Domain parsers
        from preserve.domain_parsers import DomainParserLayer
        self._domain_parsers = DomainParserLayer()

        # Layer 2e: Allow-list
        if config.use_allowlist:
            from preserve.allowlist import AllowList
            self._allowlist = AllowList(custom_allowed=config.custom_allowed or None)

        # Layer 2h: Hybrid name scorer
        self._name_scorer = None
        if config.use_name_scorer:
            from preserve.name_scorer import HybridNameScorer
            self._name_scorer = HybridNameScorer()

        # Layer 3: LLM reviewer
        if config.use_llm_review:
            from preserve.llm_review import LLMReviewer
            self._llm_reviewer = LLMReviewer(
                backend=config.llm_backend,
                server_url=config.llm_server_url,
                model_path=config.llm_model_path,
                n_threads=config.llm_n_threads,
                n_threads_batch=config.llm_n_threads_batch,
                use_chat=config.llm_use_chat,
                include_examples=config.llm_include_examples,
            )

    def _load_ner(self):
        """Lazy-load spaCy NER model."""
        if self._ner_model is None:
            try:
                import spacy
                self._ner_model = spacy.load(self.config.spacy_model)
            except ImportError:
                raise ImportError(
                    "spaCy is required for NER mode. Install with: pip install spacy && "
                    f"python -m spacy download {self.config.spacy_model}"
                )
        return self._ner_model

    def detect(self, text: str) -> list[PIIMatch]:
        """Detect all PII spans using the full pipeline."""

        # === Layer 2f: Obfuscation normalization ===
        # Detect on both original and normalized text.
        # Original catches most things; normalized catches obfuscated PII.
        from preserve.obfuscation import normalize_obfuscation
        normalized_text, _ = normalize_obfuscation(text)
        scan_text = text  # Always scan original text for position accuracy
        has_obfuscation = normalized_text != text

        matches: list[PIIMatch] = []

        # === LAYER 1: Normalcy scanning ===
        suspicious_spans: list[tuple[int, int]] | None = None
        if self._normalcy_scanner:
            suspicious_spans = self._normalcy_scanner.get_suspicious_spans(
                scan_text, threshold=self.config.llm_threshold
            )

        # === LAYER 2a: Regex pattern matching ===
        matches.extend(self._detect_patterns(scan_text))

        # === LAYER 2b: Domain parsers (phonenumbers, email-validator, dateparser) ===
        if self._domain_parsers:
            matches.extend(self._detect_domain_parsers(scan_text))

        # === Known names ===
        matches.extend(self._detect_known_names(scan_text))

        # === LAYER 2h: Hybrid name scorer ===
        if self._name_scorer:
            matches.extend(self._detect_names_hybrid(scan_text))

        # === LAYER 2g: Optional NER ===
        if self.config.use_ner:
            matches.extend(self._detect_ner(scan_text))

        # === LAYER 2c: Checksum validation ===
        matches = self._validate_checksums(matches)

        # === LAYER 2d: Context-aware confidence scoring ===
        matches = self._apply_context_scoring(scan_text, matches)

        # === LAYER 2e: Allow-list filtering ===
        matches = self._apply_allowlist(matches)

        # === LAYER 3: Local LLM review ===
        # Only fires when there are suspicious regions that Layer 2 didn't cover
        # *and* the smart gate (_should_run_llm_review) judges them worth the cost.
        if self._llm_reviewer and suspicious_spans:
            uncovered_spans = self._find_uncovered_spans(
                suspicious_spans, matches
            )
            if self._should_run_llm_review(
                scan_text, suspicious_spans, uncovered_spans, matches
            ):
                llm_detections = self._llm_reviewer.review_text(
                    scan_text, uncovered_spans
                )
                for det in llm_detections:
                    if det.confidence >= 0.3:
                        matches.append(
                            PIIMatch(
                                start=det.region_start,
                                end=det.region_end,
                                matched_text=det.text,
                                pattern_name=f"llm_{det.pii_type.lower()}",
                                replacement_type=det.pii_type,
                                sensitivity=SensitivityLevel.AGGRESSIVE,
                                detection_layer="normalcy+llm",
                                confidence=det.confidence,
                            )
                        )

        # === Layer 2f (pass 2): Scan normalized text for obfuscated PII ===
        if has_obfuscation:
            norm_matches = self._detect_patterns(normalized_text)
            norm_matches.extend(self._detect_domain_parsers(normalized_text) if self._domain_parsers else [])
            for nm in norm_matches:
                # Check if this detection is new (not already found in original)
                already_found = any(
                    nm.matched_text == m.matched_text or nm.replacement_type == m.replacement_type
                    for m in matches
                    if abs(nm.start - m.start) < 50  # Rough proximity check
                )
                if not already_found:
                    # Map back: find the corresponding region in original text
                    # The obfuscated region is longer in original, so use full line/sentence
                    mapped = self._map_normalized_to_original(
                        text, normalized_text, nm
                    )
                    if mapped:
                        matches.append(mapped)

        # === Confidence threshold filter ===
        if self.config.min_confidence > 0:
            matches = [m for m in matches if m.confidence >= self.config.min_confidence]

        # === Deduplicate and sort ===
        matches = self._deduplicate(matches)
        matches.sort(key=lambda m: m.start)

        return matches

    def _detect_patterns(self, text: str) -> list[PIIMatch]:
        """Layer 2a: regex pattern matching."""
        matches: list[PIIMatch] = []
        for pattern in self._patterns + self._custom_patterns:
            for m in pattern.regex.finditer(text):
                if m.lastindex and m.lastindex >= 1:
                    start, end = m.start(1), m.end(1)
                    matched_text = m.group(1)
                else:
                    start, end = m.start(), m.end()
                    matched_text = m.group()
                matches.append(
                    PIIMatch(
                        start=start,
                        end=end,
                        matched_text=matched_text,
                        pattern_name=pattern.name,
                        replacement_type=pattern.replacement_type,
                        sensitivity=pattern.min_sensitivity,
                        detection_layer="pattern",
                    )
                )
        return matches

    def _detect_domain_parsers(self, text: str) -> list[PIIMatch]:
        """Layer 2b: domain-specific parsers."""
        matches: list[PIIMatch] = []
        for dm in self._domain_parsers.detect(text):
            matches.append(
                PIIMatch(
                    start=dm.start,
                    end=dm.end,
                    matched_text=dm.matched_text,
                    pattern_name=f"domain_{dm.parser}",
                    replacement_type=dm.pii_type,
                    sensitivity=SensitivityLevel.STANDARD,
                    detection_layer=f"domain_{dm.parser}",
                    confidence=dm.confidence,
                )
            )
        return matches

    def _detect_names_hybrid(self, text: str) -> list[PIIMatch]:
        """Layer 2h: hybrid name detection using gazetteer + word frequency."""
        matches: list[PIIMatch] = []
        for candidate in self._name_scorer.detect(text):
            matches.append(
                PIIMatch(
                    start=candidate.start,
                    end=candidate.end,
                    matched_text=candidate.text,
                    pattern_name="name_hybrid",
                    replacement_type="NAME",
                    sensitivity=SensitivityLevel.STANDARD,
                    detection_layer="name_scorer",
                    confidence=min(candidate.score, 1.0),
                )
            )
        return matches

    def _detect_known_names(self, text: str) -> list[PIIMatch]:
        """Detect names from the known-names list."""
        if not self._known_names_pattern:
            return []
        matches: list[PIIMatch] = []
        for m in self._known_names_pattern.finditer(text):
            matches.append(
                PIIMatch(
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(),
                    pattern_name="known_name",
                    replacement_type="NAME",
                    sensitivity=SensitivityLevel.MINIMAL,
                    detection_layer="known_name",
                )
            )
        return matches

    def _detect_ner(self, text: str) -> list[PIIMatch]:
        """Layer 2g: optional NER-based detection."""
        nlp = self._load_ner()
        doc = nlp(text)
        full_map = {
            "PERSON": "NAME",
            "ORG": "ORG",
            "GPE": "LOCATION",
            "DATE": "DATE",
            "FAC": "LOCATION",
        }
        allowed = set(self.config.ner_labels)
        ner_type_map = {k: v for k, v in full_map.items() if k in allowed}
        matches: list[PIIMatch] = []
        for ent in doc.ents:
            if ent.label_ in ner_type_map:
                matches.append(
                    PIIMatch(
                        start=ent.start_char,
                        end=ent.end_char,
                        matched_text=ent.text,
                        pattern_name=f"ner_{ent.label_.lower()}",
                        replacement_type=ner_type_map[ent.label_],
                        sensitivity=SensitivityLevel.AGGRESSIVE,
                        detection_layer="ner",
                    )
                )
        return matches

    @staticmethod
    def _validate_checksums(matches: list[PIIMatch]) -> list[PIIMatch]:
        """Layer 2c: validate matches that have checksum algorithms."""
        from preserve.validators import VALIDATORS

        validated: list[PIIMatch] = []
        for match in matches:
            validator = VALIDATORS.get(match.pattern_name)
            if validator:
                if validator(match.matched_text):
                    match.confidence = min(match.confidence + 0.1, 1.0)
                    validated.append(match)
                else:
                    # Checksum failed — reduce confidence but don't discard
                    # (the regex may have captured something legitimate
                    # that just doesn't have a valid check digit)
                    match.confidence = max(match.confidence - 0.3, 0.2)
                    validated.append(match)
            else:
                validated.append(match)
        return validated

    @staticmethod
    def _apply_context_scoring(text: str, matches: list[PIIMatch]) -> list[PIIMatch]:
        """Layer 2d: adjust confidence based on surrounding context."""
        from preserve.context import score_context

        for match in matches:
            match.confidence = score_context(
                text,
                match.start,
                match.end,
                match.replacement_type,
                base_confidence=match.confidence,
            )
        return matches

    def _apply_allowlist(self, matches: list[PIIMatch]) -> list[PIIMatch]:
        """Layer 2e: filter out known false positives."""
        if not self._allowlist:
            return matches
        return [
            m for m in matches
            if not self._allowlist.is_allowed(m.matched_text, m.replacement_type)
        ]

    @staticmethod
    def _map_normalized_to_original(
        original: str, normalized: str, norm_match: PIIMatch
    ) -> PIIMatch | None:
        """Map a detection from normalized text back to the original.

        Finds the region in the original text that corresponds to where
        the normalized text had a match. Since normalization expands
        or contracts text (e.g., "five five five" → "555"), we use
        the surrounding context to locate the region.
        """
        # Strategy: find the text immediately before and after the match
        # in the normalized text, then locate those anchors in the original.
        before_norm = normalized[max(0, norm_match.start - 20):norm_match.start].strip()
        after_norm = normalized[norm_match.end:norm_match.end + 20].strip()

        # Find the last occurrence of the before-anchor in original
        orig_start = 0
        if before_norm:
            # Take the last few words as anchor
            anchor = before_norm.split()[-1] if before_norm.split() else ""
            if anchor:
                idx = original.find(anchor)
                if idx >= 0:
                    orig_start = idx + len(anchor)

        # Find the first occurrence of the after-anchor in original after orig_start
        orig_end = len(original)
        if after_norm:
            anchor = after_norm.split()[0] if after_norm.split() else ""
            if anchor:
                idx = original.find(anchor, orig_start)
                if idx >= 0:
                    orig_end = idx

        # Trim whitespace from the span
        while orig_start < orig_end and original[orig_start] in ' \t\n':
            orig_start += 1
        while orig_end > orig_start and original[orig_end - 1] in ' \t\n':
            orig_end -= 1

        if orig_start >= orig_end:
            return None

        matched_text = original[orig_start:orig_end]
        return PIIMatch(
            start=orig_start,
            end=orig_end,
            matched_text=matched_text,
            pattern_name=f"obfuscated_{norm_match.pattern_name}",
            replacement_type=norm_match.replacement_type,
            sensitivity=norm_match.sensitivity,
            detection_layer="obfuscation",
            confidence=norm_match.confidence * 0.9,  # Slight penalty for indirect detection
        )

    def _should_run_llm_review(
        self,
        scan_text: str,
        suspicious_spans: list[tuple[int, int]],
        uncovered_spans: list[tuple[int, int]],
        matches: list[PIIMatch],
    ) -> bool:
        """Smart gate deciding whether Layer 3 LLM review is worth running.

        The old gate ("total uncovered chars > 5") was crude: it summed raw
        character counts across every uncovered fragment, so it fired on stray
        whitespace/punctuation and on scattered tiny gaps, and it never used the
        confidence Layer 2 had already established. This gate instead:

          1. **Content gate** — requires at least one *single* uncovered span with
             enough alphanumeric content to plausibly hold PII. Scattered fragments
             that are individually trivial no longer trigger a review.
          2. **Confidence gate** — skips review when Layer 2 already covers most of
             the suspicious region with high-confidence detections; the local LLM
             rarely adds anything there and the call isn't worth the latency.
        """
        if not uncovered_spans:
            return False

        # (1) Content gate: is any individual uncovered span substantial?
        min_chars = self.config.llm_min_uncovered_chars
        has_substantial = any(
            sum(ch.isalnum() for ch in scan_text[s:e]) >= min_chars
            for s, e in uncovered_spans
        )
        if not has_substantial:
            return False

        # (2) Confidence gate: if the suspicious region is already mostly covered
        # by confident Layer 2 matches, the residue is most likely noise.
        overlapping = [
            m
            for m in matches
            if any(m.start < e and m.end > s for s, e in suspicious_spans)
        ]
        if overlapping:
            suspicious_len = sum(e - s for s, e in suspicious_spans)
            uncovered_len = sum(e - s for s, e in uncovered_spans)
            coverage = (
                (suspicious_len - uncovered_len) / suspicious_len
                if suspicious_len
                else 0.0
            )
            mean_conf = sum(m.confidence for m in overlapping) / len(overlapping)
            if (
                coverage >= self.config.llm_skip_coverage
                and mean_conf >= self.config.llm_skip_confidence
            ):
                return False

        return True

    @staticmethod
    def _find_uncovered_spans(
        suspicious_spans: list[tuple[int, int]],
        existing_matches: list[PIIMatch],
    ) -> list[tuple[int, int]]:
        """Find suspicious spans not already covered by pattern matches."""
        if not suspicious_spans:
            return []

        covered = set()
        for m in existing_matches:
            covered.update(range(m.start, m.end))

        uncovered: list[tuple[int, int]] = []
        for start, end in suspicious_spans:
            span_positions = set(range(start, end))
            if not span_positions.issubset(covered):
                uncovered.append((start, end))

        return uncovered

    @staticmethod
    def _deduplicate(matches: list[PIIMatch]) -> list[PIIMatch]:
        """Remove overlapping matches, keeping highest confidence then longest span."""
        if not matches:
            return matches

        # Sort by confidence descending, then by length descending
        matches.sort(key=lambda m: (-m.confidence, -(m.end - m.start), m.start))

        kept: list[PIIMatch] = []
        occupied: list[tuple[int, int]] = []

        for match in matches:
            overlaps = any(
                match.start < end and match.end > start
                for start, end in occupied
            )
            if not overlaps:
                kept.append(match)
                occupied.append((match.start, match.end))

        return kept
