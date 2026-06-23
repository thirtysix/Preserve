"""Configuration for the Preserve privacy library."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SensitivityLevel(str, Enum):
    """Controls which PII pattern categories are active."""

    MINIMAL = "minimal"  # Only high-confidence structured PII (emails, SSNs, credit cards)
    STANDARD = "standard"  # + phone numbers, IP addresses, dates of birth
    AGGRESSIVE = "aggressive"  # + names (heuristic), addresses, any potential PII


class PreserveConfig(BaseModel):
    """Configuration for PII detection and scrubbing."""

    sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
    use_ner: bool = Field(
        default=False,
        description="Use spaCy NER for enhanced name/entity detection (requires spacy install)",
    )
    use_normalcy_scanner: bool = Field(
        default=True,
        description="Enable Layer 1 normalcy scanning to flag unusual text regions",
    )
    use_name_scorer: bool = Field(
        default=True,
        description="Enable hybrid name detection using name gazetteer + word frequency",
    )
    use_llm_review: bool = Field(
        default=False,
        description="Enable Layer 3 local LLM review of uncertain regions",
    )
    llm_backend: str = Field(
        default="server",
        description=(
            "'server' (native llama-server via HTTP, fastest) or "
            "'embedded' (llama-cpp-python in-process, no server needed)"
        ),
    )
    llm_server_url: str = Field(
        default="http://127.0.0.1:8090/v1",
        description="URL of the llama-server when using server backend",
    )
    llm_model_path: str = Field(
        default="models/Qwen3.5-4B-Q4_K_M.gguf",
        description=(
            "Path to a GGUF model file (used by embedded backend). "
            "Default: Qwen3.5-4B Q4_K_M (2.6 GB), the most accurate Layer 3 model "
            "(F1 0.85 on the benchmark; ~2.6s/region on GPU, slower on CPU). "
            "Use the 0.8B/2B presets for CPU-only or low-memory setups. "
            "Download from: huggingface.co/unsloth/Qwen3.5-4B-GGUF"
        ),
    )
    llm_threshold: float = Field(
        default=0.5,
        description="Normalcy score below which regions are sent to LLM review (0.0-1.0)",
    )
    llm_use_chat: bool = Field(
        default=True,
        description="Use chat completion mode (recommended for Qwen3.5 instruction-tuned models)",
    )
    llm_min_uncovered_chars: int = Field(
        default=5,
        description=(
            "Layer 3 gate: minimum number of *alphanumeric* characters in a single "
            "uncovered suspicious span before it's worth sending to LLM review. "
            "Counting alphanumerics (not raw length) avoids firing on stray whitespace "
            "or punctuation; the per-span check avoids firing on scattered fragments."
        ),
    )
    llm_skip_coverage: float = Field(
        default=0.8,
        description=(
            "Layer 3 gate: if Layer 2 already covers at least this fraction of the "
            "suspicious region (and llm_skip_confidence is also met), skip LLM review."
        ),
    )
    llm_skip_confidence: float = Field(
        default=0.85,
        description=(
            "Layer 3 gate: if Layer 2 matches overlapping the suspicious region have a "
            "mean confidence at or above this (and llm_skip_coverage is also met), skip "
            "LLM review — the region is already handled and the LLM rarely adds anything."
        ),
    )
    llm_include_examples: bool = Field(
        default=True,
        description="Include few-shot examples in LLM prompt (disable for larger models to save tokens)",
    )
    llm_n_threads: int | None = Field(
        default=None,
        description="CPU threads for token generation — embedded backend only (default: auto-detect)",
    )
    llm_n_threads_batch: int | None = Field(
        default=None,
        description="CPU threads for prompt processing — embedded backend only (default: auto-detect)",
    )
    log_scrubbed_content: bool = Field(
        default=False,
        description="Whether audit log includes original PII values (off by default for safety)",
    )
    placeholder_format: str = Field(
        default="[{type}_{id}]",
        description="Template for placeholder tokens. {type} and {id} are replaced.",
    )
    custom_patterns: list[dict] = Field(
        default_factory=list,
        description="User-supplied patterns: [{'name': str, 'regex': str, 'sensitivity': str}]",
    )
    min_confidence: float = Field(
        default=0.0,
        description="Minimum confidence threshold for detections (0.0-1.0). Detections below this are dropped.",
    )
    use_allowlist: bool = Field(
        default=True,
        description="Enable allow-list filtering to remove known false positives",
    )
    custom_allowed: list[str] = Field(
        default_factory=list,
        description="Additional strings to exclude from PII detection",
    )
    custom_safe_patterns: list[dict] = Field(
        default_factory=list,
        description="Domain-specific safe text patterns: [{'name': str, 'regex': str}]",
    )
    known_names: list[str] = Field(
        default_factory=list,
        description="Known names to always detect (e.g., from a patient database)",
    )
    spacy_model: str = Field(
        default="en_core_web_sm",
        description="spaCy model to use when use_ner=True",
    )
