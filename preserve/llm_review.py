"""
Layer 3: Local LLM review.

Uses a small local GGUF model to review text regions that scored low on
normalcy and weren't classified by regex patterns. Runs entirely locally.

Design:
- Full text sent in ONE query with >>>..<<< markers on suspicious regions
- Markers snap to word boundaries (no mid-word cuts)
- 1-2 few-shot examples selected to match the input style (not all 4)
- Slim system prompt to minimize tokens
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("preserve.llm_review")

MARK_OPEN = ">>>"
MARK_CLOSE = "<<<"

# --- Prompt instructions (embedded in user message, no system message) ---
# Using system message + /no_think caused the 0.8B model to return empty.
# Putting everything in the user message works reliably.

INSTRUCTIONS = """Extract personal information from regions marked >>>..<<<. Use surrounding text for context.
Return JSON array: [{"text": "exact match", "type": TYPE}]
Types: NAME, ADDRESS, DOB, ID_NUMBER, PASSPORT, FINANCIAL, PHONE, EMAIL, OTHER
Not PII: cities, countries, diseases, medications, blood types, job titles.
No PII found: return []"""

# --- Example bank ---
# Each example has tags for matching against input content.
# The "comprehensive" example covers 7 PII types in one shot.

EXAMPLE_BANK = [
    {
        "tags": {"NAME", "DOB", "ADDRESS", "PHONE", "PASSPORT", "FINANCIAL"},
        "id": "comprehensive",
        "input": (
            "Patient >>>Mikko Virtanen<<<, born >>>1985-03-15<<<, "
            "at >>>Fredrikinkatu 22<<<. Phone >>>+358 44 1234567<<<. "
            "Passport >>>XP4567890<<<. Account >>>FI4950000120000062<<<. "
            "Wife >>>Aino Korhonen<<<."
        ),
        "output": [
            {"text": "Mikko Virtanen", "type": "NAME"},
            {"text": "1985-03-15", "type": "DOB"},
            {"text": "Fredrikinkatu 22", "type": "ADDRESS"},
            {"text": "+358 44 1234567", "type": "PHONE"},
            {"text": "XP4567890", "type": "PASSPORT"},
            {"text": "FI4950000120000062", "type": "FINANCIAL"},
            {"text": "Aino Korhonen", "type": "NAME"},
        ],
    },
    {
        "tags": {"NAME", "ADDRESS"},
        "id": "nordic",
        "input": '>>>Pekka Korhonen<<< at >>>Mannerheimintie 42<<<. Wife >>>Sari Laine<<<.',
        "output": [
            {"text": "Pekka Korhonen", "type": "NAME"},
            {"text": "Mannerheimintie 42", "type": "ADDRESS"},
            {"text": "Sari Laine", "type": "NAME"},
        ],
    },
    {
        "tags": {"NAME", "DOB", "ADDRESS", "PASSPORT"},
        "id": "italian",
        "input": 'Patient >>>Aurora Rossi<<<, born >>>1971-04-05<<<, at >>>Via Roma 31<<<. Passport >>>CC6770619<<<.',
        "output": [
            {"text": "Aurora Rossi", "type": "NAME"},
            {"text": "1971-04-05", "type": "DOB"},
            {"text": "Via Roma 31", "type": "ADDRESS"},
            {"text": "CC6770619", "type": "PASSPORT"},
        ],
    },
    {
        "tags": {"NAME", "PHONE", "DOB"},
        "id": "asian",
        "input": '>>>Min-jun Kim<<<, phone >>>+82 10-1234-5678<<<, born >>>15/03/1985<<<.',
        "output": [
            {"text": "Min-jun Kim", "type": "NAME"},
            {"text": "+82 10-1234-5678", "type": "PHONE"},
            {"text": "15/03/1985", "type": "DOB"},
        ],
    },
    {
        "tags": {"NAME", "EMAIL", "ID_NUMBER"},
        "id": "brazilian",
        "input": 'Employee >>>João Silva<<< (>>>joao@empresa.com.br<<<). CPF: >>>123.456.789-09<<<.',
        "output": [
            {"text": "João Silva", "type": "NAME"},
            {"text": "joao@empresa.com.br", "type": "EMAIL"},
            {"text": "123.456.789-09", "type": "ID_NUMBER"},
        ],
    },
    {
        "tags": {"NAME", "ADDRESS", "FINANCIAL"},
        "id": "latin",
        "input": '>>>Sofía García<<< at >>>Calle Reforma 156<<<. Salary: >>>MXN 85,000<<<.',
        "output": [
            {"text": "Sofía García", "type": "NAME"},
            {"text": "Calle Reforma 156", "type": "ADDRESS"},
            {"text": "MXN 85,000", "type": "FINANCIAL"},
        ],
    },
]

EXAMPLE_NEGATIVE = {
    "tags": {"NONE"},
    "id": "negative",
    "input": "Treatment follows >>>standard guidelines<<<. Blood type >>>A+<<<. Prescribed >>>Metformin 500mg<<<.",
    "output": [],
}


def _snap_to_word_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand a span to the nearest word boundaries, trimming trailing junk."""
    separators = set(' \n\t.,;:()[]')
    # Expand start backward to beginning of word
    while start > 0 and text[start - 1] not in separators:
        start -= 1
    # Expand end forward to end of word
    while end < len(text) and text[end] not in separators:
        end += 1
    # Trim leading/trailing whitespace and punctuation from the span
    while start < end and text[start] in separators:
        start += 1
    while end > start and text[end - 1] in (' ', '\t'):
        end -= 1
    return start, end


def mark_text(full_text: str, suspicious_spans: list[tuple[int, int]]) -> tuple[str, list[dict]]:
    """Insert >>><<< markers around suspicious spans, snapped to word boundaries.

    Returns (marked_text, region_map).
    """
    if not suspicious_spans:
        return full_text, []

    # Snap each span to word boundaries
    snapped = [_snap_to_word_boundaries(full_text, s, e) for s, e in suspicious_spans]

    # Sort and merge overlapping
    snapped.sort(key=lambda s: s[0])
    merged: list[tuple[int, int]] = [snapped[0]]
    for start, end in snapped[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Build marked text
    region_map: list[dict] = []
    parts: list[str] = []
    prev_end = 0

    for i, (start, end) in enumerate(merged, 1):
        parts.append(full_text[prev_end:start])
        region_text = full_text[start:end]
        parts.append(f"{MARK_OPEN}{region_text}{MARK_CLOSE}")
        region_map.append({
            "region": i,
            "start": start,
            "end": end,
            "text": region_text,
        })
        prev_end = end

    parts.append(full_text[prev_end:])
    return "".join(parts), region_map


def _select_examples(marked_text: str, max_positive: int = 1) -> list[dict]:
    """Select the most relevant examples from the bank.

    Scores each example by tag overlap with likely PII types in the input,
    then returns the top match(es) plus the negative example.
    """
    text_lower = marked_text.lower()
    likely_tags: set[str] = set()

    if re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', marked_text):
        likely_tags.add("NAME")
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}', marked_text):
        likely_tags.add("DOB")
    if re.search(r'\d+\s+\w+(?:street|road|ave|via|calle|rue|straße|katu|gracht|intie)', text_lower):
        likely_tags.add("ADDRESS")
    if re.search(r'[+\d][\d\s\-()]{7,}', marked_text):
        likely_tags.add("PHONE")
    if '@' in marked_text:
        likely_tags.add("EMAIL")
    if re.search(r'passport|id|cpf|nino|ssn|bsn|dni', text_lower):
        likely_tags.add("ID_NUMBER")
        likely_tags.add("PASSPORT")
    if re.search(r'[\$€£¥₹]\s*\d|salary|income|iban|account', text_lower):
        likely_tags.add("FINANCIAL")

    if not likely_tags:
        likely_tags.add("NAME")

    scored = []
    for ex in EXAMPLE_BANK:
        overlap = len(ex["tags"] & likely_tags)
        scored.append((overlap, ex))

    scored.sort(key=lambda x: -x[0])
    selected = [ex for _, ex in scored[:max_positive]]
    selected.append(EXAMPLE_NEGATIVE)
    return selected


def build_chat_prompt(
    marked_text: str,
    mode: str = "comprehensive",
) -> list[dict]:
    """Build a chat prompt. All content in a single user message (no system message).

    Args:
        marked_text: Text with >>><<< markers.
        mode: "comprehensive" = single dense example + negative.
              "selected" = 1-2 best-matching examples from bank + negative.
    """
    if mode == "selected":
        examples = _select_examples(marked_text, max_positive=2)
    else:
        examples = [EXAMPLE_BANK[0], EXAMPLE_NEGATIVE]

    parts = [INSTRUCTIONS, ""]
    for ex in examples:
        parts.append(f"Input: {ex['input']}")
        parts.append(f"Output: {json.dumps(ex['output'])}")
        parts.append("")
    parts.append(f"Input: {marked_text}")
    parts.append("Output:")

    return [{"role": "user", "content": "\n".join(parts)}]


def build_prompt(
    marked_text: str,
    include_examples: bool = True,
    mode: str = "comprehensive",
) -> str:
    """Build a completion-format prompt."""
    parts = [INSTRUCTIONS, ""]

    if include_examples:
        if mode == "selected":
            examples = _select_examples(marked_text, max_positive=2)
        else:
            examples = [EXAMPLE_BANK[0], EXAMPLE_NEGATIVE]

        for ex in examples:
            parts.append(f"Input: {ex['input']}")
            parts.append(f"Output: {json.dumps(ex['output'])}")
            parts.append("")

    parts.append(f"Input: {marked_text}")
    parts.append("Output:")

    return "\n".join(parts)


@dataclass
class LLMDetection:
    """A PII detection from the local LLM."""

    text: str
    pii_type: str
    confidence: float
    region_start: int
    region_end: int


def _detect_cpu_threads() -> tuple[int, int]:
    """Detect conservative thread counts."""
    import os
    logical = os.cpu_count() or 4
    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
        cores = re.search(r"cpu cores\s*:\s*(\d+)", content)
        physical = int(cores.group(1)) if cores else logical // 2
    except (FileNotFoundError, AttributeError):
        physical = logical // 2
    safe = max(2, physical // 2)
    return safe, safe


class LLMReviewer:
    """Reviews suspicious text regions using a local LLM.

    Backends:
    - "server": Native llama-server via HTTP (fastest, GPU support)
    - "embedded": llama-cpp-python in-process (no server needed)
    """

    def __init__(
        self,
        backend: str = "server",
        server_url: str = "http://127.0.0.1:8090/v1",
        model_path: str = "",
        n_ctx: int = 4096,
        n_threads: int | None = None,
        n_threads_batch: int | None = None,
        use_chat: bool = True,
        include_examples: bool = True,
        prompt_mode: str = "selected",
    ) -> None:
        self._backend = backend
        self._server_url = server_url
        self._model_path = model_path
        self._model = None
        self._client = None
        self._n_ctx = n_ctx
        self._use_chat = use_chat
        self._include_examples = include_examples
        self._prompt_mode = prompt_mode  # "comprehensive" or "selected"

        if backend == "embedded":
            if n_threads is None or n_threads_batch is None:
                phys, logical = _detect_cpu_threads()
                self._n_threads = n_threads or phys
                self._n_threads_batch = n_threads_batch or logical
            else:
                self._n_threads = n_threads
                self._n_threads_batch = n_threads_batch

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self._server_url, api_key="not-needed")
        return self._client

    def _load_embedded_model(self):
        if self._model is None:
            try:
                from llama_cpp import Llama
            except ImportError:
                raise ImportError(
                    "llama-cpp-python is required for embedded backend. "
                    "Install with: pip install llama-cpp-python"
                )
            logger.info("Loading GGUF model from %s", self._model_path)
            self._model = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                n_threads_batch=self._n_threads_batch,
                use_mmap=True,
                use_mlock=True,
                flash_attn=True,
                verbose=False,
                seed=42,
            )
        return self._model

    def review_text(
        self,
        full_text: str,
        suspicious_spans: list[tuple[int, int]],
        max_marked_chars: int = 120,
        context_chars: int = 60,
    ) -> list[LLMDetection]:
        """Review suspicious regions with surrounding context."""
        if not suspicious_spans:
            return []

        model = self._load_embedded_model() if self._backend == "embedded" else None

        # Merge overlapping spans (word-boundary snapping happens in mark_text)
        spans = sorted(suspicious_spans, key=lambda s: s[0])
        merged: list[tuple[int, int]] = [spans[0]]
        for start, end in spans[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        # Split large spans into smaller windows
        small_spans: list[tuple[int, int]] = []
        for start, end in merged:
            if end - start <= max_marked_chars:
                small_spans.append((start, end))
            else:
                pos = start
                while pos < end:
                    chunk_end = min(pos + max_marked_chars, end)
                    if chunk_end < end:
                        for sep in ('. ', ', ', ' '):
                            last_sep = full_text[pos:chunk_end].rfind(sep)
                            if last_sep > 0:
                                chunk_end = pos + last_sep + len(sep)
                                break
                    small_spans.append((pos, chunk_end))
                    pos = chunk_end

        all_detections: list[LLMDetection] = []
        for span_start, span_end in small_spans:
            window_start = max(0, span_start - context_chars)
            window_end = min(len(full_text), span_end + context_chars)

            # Snap context window to word boundaries
            while window_start > 0 and full_text[window_start] not in (' ', '.', '\n'):
                window_start -= 1
            while window_end < len(full_text) and full_text[window_end] not in (' ', '.', '\n'):
                window_end += 1

            chunk_text = full_text[window_start:window_end]
            adjusted_span = (span_start - window_start, span_end - window_start)

            detections = self._review_chunk(model, chunk_text, [adjusted_span])

            for det in detections:
                det.region_start += window_start
                det.region_end += window_start

            all_detections.extend(detections)

        return all_detections

    def _review_chunk(self, model, text: str, spans: list[tuple[int, int]]) -> list[LLMDetection]:
        """Send a single query via the active backend."""
        marked_text, region_map = mark_text(text, spans)
        if not region_map:
            return []

        if self._backend == "server":
            raw_output = self._call_server(marked_text)
        elif self._use_chat and model is not None:
            messages = build_chat_prompt(marked_text, mode=self._prompt_mode)
            response = model.create_chat_completion(
                messages=messages, max_tokens=256, temperature=0.0,
            )
            raw_output = response["choices"][0]["message"]["content"].strip()
        elif model is not None:
            prompt = build_prompt(
                marked_text, include_examples=self._include_examples,
                mode=self._prompt_mode,
            )
            response = model(
                prompt, max_tokens=256, temperature=0.0,
                stop=["\n\nInput:"],
            )
            raw_output = response["choices"][0]["text"].strip()
        else:
            return []

        return self._parse_response(raw_output, region_map)

    def _call_server(self, marked_text: str) -> str:
        """Call llama-server via OpenAI-compatible API."""
        client = self._get_client()
        messages = build_chat_prompt(marked_text, mode=self._prompt_mode)
        try:
            response = client.chat.completions.create(
                model="local", messages=messages,
                max_tokens=256, temperature=0.0, seed=42,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("llama-server call failed: %s", e)
            return "[]"

    def review_region(self, text: str, region_start: int = 0) -> list[LLMDetection]:
        """Review a single text region (legacy interface)."""
        return self.review_text(text, [(0, len(text))])

    def review_regions(self, regions: list[tuple[int, int, str]]) -> list[LLMDetection]:
        """Review multiple regions (legacy interface)."""
        all_detections: list[LLMDetection] = []
        for start, end, text in regions:
            detections = self.review_region(text, region_start=start)
            all_detections.extend(detections)
        return all_detections

    def _parse_response(self, raw: str, region_map: list[dict]) -> list[LLMDetection]:
        """Parse LLM JSON output into detections."""
        detections: list[LLMDetection] = []

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        items = self._try_parse_json(cleaned)
        if items is None:
            items = self._try_parse_jsonl(cleaned)
        if items is None:
            items = self._try_extract_array(cleaned)
        if items is None:
            logger.debug("Could not parse LLM response: %s", raw[:300])
            return detections

        region_lookup = {r["region"]: r for r in region_map}

        for item in items:
            if not isinstance(item, dict) or "text" not in item:
                continue

            pii_text = str(item["text"])
            pii_type = self._normalize_type(str(item.get("type", "OTHER")).upper())
            confidence = float(item.get("confidence", 0.5))
            region_num = item.get("region")

            region = None
            if region_num and region_num in region_lookup:
                region = region_lookup[region_num]
            else:
                for r in region_map:
                    if pii_text.lower() in r["text"].lower():
                        region = r
                        break

            if region:
                idx = self._find_in_source(pii_text, region["text"])
                if idx >= 0:
                    abs_start = region["start"] + idx
                    detections.append(LLMDetection(
                        text=region["text"][idx:idx + len(pii_text)],
                        pii_type=pii_type,
                        confidence=confidence,
                        region_start=abs_start,
                        region_end=abs_start + len(pii_text),
                    ))

        return detections

    @staticmethod
    def _try_parse_json(text: str) -> list[dict] | None:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("pii", [data] if "text" in data else None)
            return None
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _try_parse_jsonl(text: str) -> list[dict] | None:
        items = []
        for line in text.strip().split("\n"):
            line = line.strip().rstrip(",")
            if not line or line in ("[]", "[", "]"):
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "text" in obj:
                    items.append(obj)
            except (json.JSONDecodeError, ValueError):
                continue
        return items if items else None

    @staticmethod
    def _try_extract_array(text: str) -> list[dict] | None:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    @staticmethod
    def _find_in_source(pii_text: str, source: str) -> int:
        idx = source.find(pii_text)
        if idx >= 0:
            return idx
        idx = source.lower().find(pii_text.lower())
        if idx >= 0:
            return idx
        stripped = pii_text.strip(" .,;:\"'")
        if stripped != pii_text:
            idx = source.find(stripped)
            if idx >= 0:
                return idx
        return -1

    @staticmethod
    def _normalize_type(pii_type: str) -> str:
        aliases = {
            "PERSON": "NAME", "PERSON_NAME": "NAME", "FULL_NAME": "NAME",
            "FIRST_NAME": "NAME", "LAST_NAME": "NAME", "SURNAME": "NAME",
            "STREET_ADDRESS": "ADDRESS", "HOME_ADDRESS": "ADDRESS", "LOCATION": "ADDRESS",
            "DATE_OF_BIRTH": "DOB", "BIRTHDAY": "DOB", "BIRTH_DATE": "DOB", "DATE": "DOB",
            "SSN": "ID_NUMBER", "NATIONAL_ID": "ID_NUMBER", "IDENTITY_NUMBER": "ID_NUMBER",
            "TAX_ID": "ID_NUMBER", "DRIVERS_LICENSE": "ID_NUMBER",
            "BANK_ACCOUNT": "FINANCIAL", "CREDIT_CARD": "FINANCIAL",
            "IBAN": "FINANCIAL", "SALARY": "FINANCIAL", "INCOME": "FINANCIAL",
            "PHONE_NUMBER": "PHONE", "TELEPHONE": "PHONE", "MOBILE": "PHONE",
            "EMAIL_ADDRESS": "EMAIL",
            "HEALTH": "MEDICAL", "DIAGNOSIS": "MEDICAL", "MEDICATION": "MEDICAL",
            "PASSPORT_NUMBER": "PASSPORT",
        }
        return aliases.get(pii_type, pii_type)
