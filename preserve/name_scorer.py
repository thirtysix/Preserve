"""
Layer 2h: Hybrid name detection.

Combines multiple signals to detect personal names:
- Name gazetteer (names-dataset): is this token a known first/last name?
- Word frequency (wordfreq): is this token a rare word? (rare = likely proper noun)
- Capitalization patterns + lowercase fallback via gazetteer
- Language-specific suffix patterns: -nen, -ez, -ov, etc.
- Initial + surname patterns: "J. Smith", "A. Rossi"

Handles both clean and messy input (no caps, typos, abbreviations).
Runs in <10ms per document. ~150 MB RAM for the loaded datasets.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger("preserve.name_scorer")

# Letter ranges covering Latin-1 plus Latin Extended-A (Polish, Turkish, Czech,
# Romanian, ...) so names like "Stępniak", "Sarı", "İlhan" tokenize fully rather
# than truncating at the first non-Latin-1 character.
_UP = "A-ZÀ-ÖØ-ÞĀ-ſ"
_LO = "a-zà-öø-ÿĀ-ſ"

# Language-specific surname suffixes
SURNAME_SUFFIXES = re.compile(
    r"(?:nen|la|lä|sto"          # Finnish
    r"|son|sen|ström|berg|lund|qvist"  # Nordic
    r"|ez|az"                    # Hispanic
    r"|ov|ova|ski|ska|vich|enko" # Slavic
    r"|ian|yan"                  # Armenian
    r"|ou|is|os"                 # Greek
    r"|ić|ović"                  # South Slavic
    r")$",
    re.IGNORECASE,
)

# Context keywords preceding names
NAME_CONTEXT = re.compile(
    r"\b(?:patient|client|employee|name|contact|witness|supervisor|"
    r"manager|doctor|nurse|attorney|signed by|referred by|"
    r"mr|mrs|ms|miss|dr|prof|"
    r"wife|husband|spouse|mother|father|son|daughter|"
    r"caller|attendee|participant|sender|recipient|"
    r"pt|emp|attn|fwd|re|cc)\s*[:\.\s]?\s*$",
    re.IGNORECASE,
)

# Words that are context labels, not names
CONTEXT_WORDS = {
    "patient", "client", "employee", "name", "contact", "witness",
    "supervisor", "manager", "doctor", "nurse", "attorney",
    "applicant", "customer", "user", "beneficiary", "spouse",
    "guardian", "dependent", "plaintiff", "defendant",
    "caller", "attendee", "participant", "sender", "recipient",
}

# Tokens to always skip
SKIP_TOKENS = {
    "the", "a", "an", "and", "or", "but", "for", "nor", "yet", "so",
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might",
    "this", "that", "these", "those", "it", "its",
    "not", "no", "yes", "all", "any", "each", "every",
    "i", "we", "you", "he", "she", "they", "me", "us", "him", "her", "them",
    "my", "our", "your", "his", "their",
    "who", "what", "where", "when", "why", "how",
    "if", "then", "else", "than", "as", "at", "by", "in", "on", "to", "of",
    "with", "from", "into", "about", "between", "through", "during",
    "before", "after", "above", "below", "up", "down", "out", "off",
    "over", "under", "again", "further", "once",
    "new", "old", "best", "first", "last", "next", "good", "great",
    "long", "high", "low", "big", "small", "own", "just", "also",
    "north", "south", "east", "west",
    # Common verbs/words that appear in messy text
    "need", "want", "called", "said", "told", "asked", "check",
    "send", "get", "got", "put", "take", "look", "see", "know",
    "think", "like", "lol", "ok", "hey", "hi", "pls", "thx", "thanks",
    "re", "fwd", "cc", "subject", "from",
    # Common geographic/place words that aren't person names
    "helsinki", "finland", "europe", "asia", "africa", "america",
    "london", "paris", "berlin", "rome", "tokyo", "moscow",
    "stockholm", "oslo", "copenhagen", "amsterdam", "brussels",
    "madrid", "lisbon", "vienna", "prague", "warsaw", "budapest",
    "attendees", "participants", "conference", "meeting",
}

# Initial + surname pattern: "J. Smith", "A. Rossi", "Mr. V"
INITIAL_SURNAME = re.compile(
    rf"\b([{_UP}])\.\s*([{_UP}][{_LO}]{{2,}})\b"
)

# Parenthetical name reveal: "Mr. V (Virtanen)"
PAREN_NAME = re.compile(
    rf"\b([{_UP}{_LO}]+)\s*\(([{_UP}][{_LO}]+)\)"
)


@dataclass
class NameCandidate:
    """A potential name detected by the hybrid scorer."""

    start: int
    end: int
    text: str
    score: float
    signals: list[str]


class HybridNameScorer:
    """Detects personal names using dictionary + frequency + heuristic signals."""

    def __init__(self, languages: list[str] | None = None) -> None:
        from names_dataset import NameDataset
        from wordfreq import zipf_frequency

        self._nd = NameDataset()
        self._zipf = zipf_frequency
        self._languages = languages or ["en"]

        logger.info("HybridNameScorer loaded (languages: %s)", self._languages)

    def detect(self, text: str, min_score: float = 0.5) -> list[NameCandidate]:
        """Find name candidates in text."""
        candidates: list[NameCandidate] = []

        # Pass 1: Capitalized words (standard case)
        candidates.extend(self._detect_capitalized(text, min_score))

        # Pass 2: Lowercase name pairs via gazetteer
        candidates.extend(self._detect_lowercase_names(text, min_score))

        # Pass 3: Initial + surname patterns ("J. Smith", "A. Rossi")
        candidates.extend(self._detect_initials(text))

        # Pass 4: Parenthetical reveals ("Mr. V (Virtanen)")
        candidates.extend(self._detect_paren_names(text))

        # Pass 5: Single lowercase names after context keywords ("mrs korhonen")
        candidates.extend(self._detect_context_single_names(text))

        # Deduplicate overlapping candidates (keep highest score)
        candidates = self._deduplicate(candidates)

        return candidates

    def _detect_capitalized(self, text: str, min_score: float) -> list[NameCandidate]:
        """Pass 1: Find capitalized word sequences that look like names."""
        candidates: list[NameCandidate] = []
        tokens = list(self._tokenize_capitalized(text))

        i = 0
        while i < len(tokens):
            start, end, token = tokens[i]

            if token.lower() in SKIP_TOKENS or token.lower() in CONTEXT_WORDS:
                i += 1
                continue

            # Try multi-word name
            name_tokens = [(start, end, token)]
            j = i + 1
            while j < len(tokens):
                next_start, next_end, next_token = tokens[j]
                if (next_start - name_tokens[-1][1] <= 2
                        and next_token.lower() not in SKIP_TOKENS
                        and next_token.lower() not in CONTEXT_WORDS):
                    name_tokens.append((next_start, next_end, next_token))
                    j += 1
                else:
                    break

            if len(name_tokens) >= 2:
                full_start = name_tokens[0][0]
                full_end = name_tokens[-1][1]
                full_text = text[full_start:full_end]
                score, signals = self._score_name(
                    [t for _, _, t in name_tokens], text, full_start
                )
                if score >= min_score:
                    candidates.append(NameCandidate(
                        full_start, full_end, full_text, score, signals,
                    ))
                i = j
            else:
                score, signals = self._score_name([token], text, start)
                if score >= min_score + 0.1:
                    candidates.append(NameCandidate(
                        start, end, token, score, signals,
                    ))
                i += 1

        return candidates

    def _detect_lowercase_names(self, text: str, min_score: float) -> list[NameCandidate]:
        """Pass 2: Find lowercase word pairs that match the name gazetteer.

        For messy input like "aurora rossi" or "mikko virtanen" without caps.
        Requires BOTH words to be in the name database to avoid false positives.
        """
        candidates: list[NameCandidate] = []

        # Tokenize all words (including lowercase)
        words = list(re.finditer(rf"\b([{_UP}{_LO}]{{2,}})\b", text))

        for i in range(len(words) - 1):
            w1 = words[i]
            w2 = words[i + 1]

            t1 = w1.group()
            t2 = w2.group()

            # Skip if already capitalized (handled by pass 1)
            if t1[0].isupper() and t2[0].isupper():
                continue

            # Skip common words
            if t1.lower() in SKIP_TOKENS or t2.lower() in SKIP_TOKENS:
                continue
            if t1.lower() in CONTEXT_WORDS or t2.lower() in CONTEXT_WORDS:
                continue

            # Must be adjacent, separated only by whitespace/comma (a name pair
            # should not span punctuation like ":" in "aa:bb:cc:dd:ee:ff").
            if w2.start() - w1.end() > 2:
                continue
            if not re.fullmatch(r"[\s,]*", text[w1.end():w2.start()]):
                continue

            # Both must be in the name gazetteer
            r1 = self._nd.search(t1.capitalize())
            r2 = self._nd.search(t2.capitalize())

            is_first_1 = bool(r1.get("first_name"))
            is_last_2 = bool(r2.get("last_name"))
            is_first_2 = bool(r2.get("first_name"))
            is_last_1 = bool(r1.get("last_name"))

            # Pattern: first_name + last_name OR last_name + first_name
            if (is_first_1 and is_last_2) or (is_last_1 and is_first_2):
                freq1 = max(self._zipf(t1.lower(), lang) for lang in self._languages)
                freq2 = max(self._zipf(t2.lower(), lang) for lang in self._languages)

                # Skip if both are extremely common (> 6.0 = top ~1000 words)
                # But allow "john smith" (5.4 + 4.9) — names CAN be common words
                if freq1 > 6.0 and freq2 > 6.0:
                    continue  # Both are too common ("will may", "can do")

                score = 0.35  # Base for lowercase gazetteer match
                signals = ["lowercase_pair"]

                # Bonus for rare words
                if freq1 < 3.0:
                    score += 0.2
                    signals.append(f"rare({t1})")
                elif freq1 < 4.0:
                    score += 0.1
                    signals.append(f"uncommon({t1})")
                if freq2 < 3.0:
                    score += 0.2
                    signals.append(f"rare({t2})")
                elif freq2 < 4.0:
                    score += 0.1
                    signals.append(f"uncommon({t2})")

                # Context boost
                before = text[max(0, w1.start() - 40):w1.start()]
                if NAME_CONTEXT.search(before):
                    score += 0.4
                    signals.append("context")

                # Surname suffix boost
                if SURNAME_SUFFIXES.search(t2):
                    score += 0.1
                    signals.append("surname_suffix")

                if score >= min_score:
                    full_text = text[w1.start():w2.end()]
                    candidates.append(NameCandidate(
                        w1.start(), w2.end(), full_text, score, signals,
                    ))

        return candidates

    def _detect_initials(self, text: str) -> list[NameCandidate]:
        """Pass 3: Find 'J. Smith', 'A. Rossi' patterns."""
        candidates: list[NameCandidate] = []

        for m in INITIAL_SURNAME.finditer(text):
            surname = m.group(2)
            result = self._nd.search(surname)
            if result.get("last_name") or result.get("first_name"):
                candidates.append(NameCandidate(
                    m.start(), m.end(), m.group(),
                    score=0.7, signals=["initial_surname"],
                ))

        return candidates

    def _detect_paren_names(self, text: str) -> list[NameCandidate]:
        """Pass 4: Find 'V (Virtanen)' parenthetical name reveals."""
        candidates: list[NameCandidate] = []

        for m in PAREN_NAME.finditer(text):
            name_in_parens = m.group(2)
            result = self._nd.search(name_in_parens)
            if result.get("last_name") or result.get("first_name"):
                candidates.append(NameCandidate(
                    m.start(), m.end(), m.group(),
                    score=0.8, signals=["paren_reveal"],
                ))

        return candidates

    # Titles that indicate a name follows
    _TITLE_WORDS = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir", "lady"}
    # Context words that indicate a name follows (but aren't titles)
    _NAME_INTRO_WORDS = {
        "wife", "husband", "mother", "father", "son", "daughter",
        "patient", "pt", "caller", "contact", "employee", "emp", "attn",
    }

    def _detect_context_single_names(self, text: str) -> list[NameCandidate]:
        """Pass 5: Single names after title/context keywords.

        Handles chains: 'mrs korhonen', 'wife maria', 'contact mrs korhonen'
        """
        candidates: list[NameCandidate] = []
        all_keywords = self._TITLE_WORDS | self._NAME_INTRO_WORDS

        words = list(re.finditer(rf"\b([{_UP}{_LO}]{{2,}})\b", text))

        for i, w in enumerate(words):
            token = w.group().lower()
            if token not in all_keywords:
                continue

            # Look at the next 1-2 words for a name
            # Skip over titles: "contact mrs korhonen" → skip "mrs", get "korhonen"
            for j in range(i + 1, min(i + 3, len(words))):
                next_word = words[j].group()
                next_lower = next_word.lower()

                # Skip titles in the chain
                if next_lower in self._TITLE_WORDS:
                    continue
                # Skip other context words
                if next_lower in self._NAME_INTRO_WORDS or next_lower in CONTEXT_WORDS:
                    continue
                if next_lower in SKIP_TOKENS:
                    continue

                # Check adjacency
                if words[j].start() - words[j - 1].end() > 3:
                    break

                # Check if it's a name
                result = self._nd.search(next_word.capitalize())
                if result.get("first_name") or result.get("last_name"):
                    candidates.append(NameCandidate(
                        words[j].start(), words[j].end(), next_word,
                        score=0.7, signals=["context_single_name"],
                    ))
                break  # Only take the first real name after keywords

        return candidates

    def _score_name(
        self, tokens: list[str], full_text: str, start_pos: int
    ) -> tuple[float, list[str]]:
        """Score a candidate name. Returns (score, signals)."""
        score = 0.0
        signals: list[str] = []

        for token in tokens:
            result = self._nd.search(token)
            is_first = bool(result.get("first_name"))
            is_last = bool(result.get("last_name"))

            if is_first or is_last:
                country_data = result.get("first_name", {}) or result.get("last_name", {})
                if isinstance(country_data, dict) and len(country_data) > 3:
                    score += 0.4
                    signals.append(f"gazetteer({token})")
                else:
                    score += 0.25
                    signals.append(f"gazetteer_weak({token})")

            max_freq = max(
                self._zipf(token.lower(), lang) for lang in self._languages
            )
            if max_freq < 2.0:
                score += 0.3
                signals.append(f"rare({token})")
            elif max_freq < 3.5:
                score += 0.15
                signals.append(f"uncommon({token})")

            if max_freq > 4.0 and (is_first or is_last):
                score -= 0.3
                signals.append(f"common_word({token})")

            if SURNAME_SUFFIXES.search(token):
                score += 0.1
                signals.append(f"suffix({token})")

        if len(tokens) >= 2:
            score += 0.2
            signals.append("multi_word")

        before = full_text[max(0, start_pos - 40):start_pos]
        if NAME_CONTEXT.search(before):
            score += 0.4
            signals.append("context")

        if start_pos == 0 or full_text[start_pos - 1] in '.!?\n':
            if len(tokens) == 1:
                score -= 0.2
                signals.append("sentence_initial")

        return score, signals

    @staticmethod
    def _tokenize_capitalized(text: str) -> list[tuple[int, int, str]]:
        """Find capitalized words including hyphenated names."""
        results = []
        for m in re.finditer(
            rf"\b([{_UP}][{_LO}]+(?:-[{_UP}{_LO}]+)*)\b", text
        ):
            results.append((m.start(), m.end(), m.group()))
        return results

    @staticmethod
    def _deduplicate(candidates: list[NameCandidate]) -> list[NameCandidate]:
        """Remove overlapping candidates, keeping highest score."""
        if not candidates:
            return candidates

        candidates.sort(key=lambda c: (-c.score, c.start))
        kept: list[NameCandidate] = []
        occupied: list[tuple[int, int]] = []

        for c in candidates:
            overlaps = any(c.start < end and c.end > start for start, end in occupied)
            if not overlaps:
                kept.append(c)
                occupied.append((c.start, c.end))

        return kept
