"""Preserve API gateway — a privacy-preserving LLM proxy.

A central FastAPI service that scrubs PII from prompts, forwards the
sanitized text to an upstream LLM, and restores PII in the response.
PII stays inside the organization and never reaches the third-party LLM.

Run with:  uvicorn preserve.api.app:app  (see scripts/run_api.sh)
"""

from preserve.api.app import app, create_app

__all__ = ["app", "create_app"]
