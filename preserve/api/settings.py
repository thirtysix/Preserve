"""Configuration for the Preserve API gateway, loaded from environment.

Environment variables
---------------------
PRESERVE_UPSTREAM_BASE_URL   Upstream OpenAI-compatible LLM base URL
                             (default: DeepInfra).
PRESERVE_UPSTREAM_API_KEY    Org's key for the upstream LLM. Falls back to
                             DEEPINFRA_API_KEY. Users never see this.
PRESERVE_DEFAULT_MODEL       Model used when a request omits "model".
PRESERVE_SENSITIVITY         minimal | standard | aggressive (default: standard).
PRESERVE_USE_NAME_SCORER     "1"/"0" — enable the gazetteer name scorer (default 1).
PRESERVE_MAX_INPUT_CHARS     Reject requests whose combined input exceeds this.

PRESERVE_API_KEYS            JSON: {"<key>": {"name": str, "rpm": int,
                             "daily_token_quota": int}, ...}
PRESERVE_API_KEYS_FILE       Path to a JSON file with the same shape.
PRESERVE_ALLOW_NO_AUTH       "1" to disable auth (DEV ONLY — logs a warning).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from preserve.config import PreserveConfig, SensitivityLevel

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
logger = logging.getLogger("preserve.api")

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"


@dataclass(frozen=True)
class APIKey:
    """A gateway API key and its per-principal limits."""

    key: str
    name: str
    rpm: int = 60                      # requests per minute
    daily_token_quota: int = 1_000_000  # upstream tokens per UTC day (0 = unlimited)


@dataclass
class APISettings:
    upstream_base_url: str = DEEPINFRA_BASE_URL
    upstream_api_key: str = ""
    default_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    sensitivity: SensitivityLevel = SensitivityLevel.STANDARD
    use_name_scorer: bool = True
    max_input_chars: int = 100_000
    allow_no_auth: bool = False
    keys: dict[str, APIKey] = field(default_factory=dict)

    def preserve_config(self) -> PreserveConfig:
        """The detection config the gateway scrubs with (LLM review off — the
        gateway forwards to the real upstream model instead)."""
        return PreserveConfig(
            sensitivity_level=self.sensitivity,
            use_name_scorer=self.use_name_scorer,
            use_llm_review=False,
            log_scrubbed_content=False,  # never log PII values
        )


def _load_keys() -> dict[str, APIKey]:
    raw = os.environ.get("PRESERVE_API_KEYS")
    if not raw and os.environ.get("PRESERVE_API_KEYS_FILE"):
        path = Path(os.environ["PRESERVE_API_KEYS_FILE"])
        if path.exists():
            raw = path.read_text()
    if not raw:
        return {}
    data = json.loads(raw)
    keys: dict[str, APIKey] = {}
    for key, meta in data.items():
        meta = meta or {}
        keys[key] = APIKey(
            key=key,
            name=meta.get("name", "unnamed"),
            rpm=int(meta.get("rpm", 60)),
            daily_token_quota=int(meta.get("daily_token_quota", 1_000_000)),
        )
    return keys


def get_settings() -> APISettings:
    """Build settings from the environment."""
    sens = os.environ.get("PRESERVE_SENSITIVITY", "standard").lower()
    allow_no_auth = os.environ.get("PRESERVE_ALLOW_NO_AUTH") == "1"
    keys = _load_keys()
    if allow_no_auth:
        logger.warning("PRESERVE_ALLOW_NO_AUTH=1 — authentication is DISABLED. Dev only.")
    elif not keys:
        logger.warning("No API keys configured (PRESERVE_API_KEYS). All requests will be rejected.")

    return APISettings(
        upstream_base_url=os.environ.get("PRESERVE_UPSTREAM_BASE_URL", DEEPINFRA_BASE_URL),
        upstream_api_key=os.environ.get("PRESERVE_UPSTREAM_API_KEY")
                         or os.environ.get("DEEPINFRA_API_KEY", ""),
        default_model=os.environ.get("PRESERVE_DEFAULT_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        sensitivity=SensitivityLevel(sens),
        use_name_scorer=os.environ.get("PRESERVE_USE_NAME_SCORER", "1") != "0",
        max_input_chars=int(os.environ.get("PRESERVE_MAX_INPUT_CHARS", "100000")),
        allow_no_auth=allow_no_auth,
        keys=keys,
    )
