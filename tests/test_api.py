"""Tests for the Preserve API gateway (preserve.api)."""

import types

import pytest
from fastapi.testclient import TestClient

from preserve.api.app import create_app
from preserve.api.settings import APIKey, APISettings
from preserve.config import SensitivityLevel


# --- Fake upstream LLM (records what it receives, echoes a placeholder back) ---
class _FakeCompletions:
    def __init__(self):
        self.last = None

    def create(self, model, messages, **kw):
        self.last = {"model": model, "messages": messages, "kw": kw}
        # Echo the final user message back (it still contains placeholders)
        content = "Re: " + messages[-1]["content"]
        return types.SimpleNamespace(model_dump=lambda: {
            "id": "chatcmpl-test", "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        })


class _FakeUpstream:
    def __init__(self):
        self.chat = types.SimpleNamespace(completions=_FakeCompletions())


def make_client(rpm=60, daily=1_000_000, with_upstream=True):
    settings = APISettings(
        upstream_api_key="test-upstream-key",
        default_model="test-model",
        sensitivity=SensitivityLevel.STANDARD,
        use_name_scorer=False,  # keep tests fast/deterministic (regex only)
        keys={"k-test": APIKey(key="k-test", name="tester", rpm=rpm, daily_token_quota=daily)},
    )
    app = create_app(settings)
    fake = _FakeUpstream()
    if with_upstream:
        app.state._upstream = fake
    client = TestClient(app, raise_server_exceptions=True)
    return client, fake


AUTH = {"Authorization": "Bearer k-test"}


def test_health():
    client, _ = make_client()
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_auth_required():
    client, _ = make_client()
    assert client.post("/v1/scrub", json={"text": "x"}).status_code == 401
    assert client.post("/v1/scrub", json={"text": "x"},
                       headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_scrub_and_restore_roundtrip():
    client, _ = make_client()
    r = client.post("/v1/scrub",
                    json={"text": "Email me at jane@acme.com or SSN 123-45-6789"},
                    headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert "jane@acme.com" not in body["sanitized_text"]
    assert "[EMAIL_1]" in body["sanitized_text"]
    assert body["pii_count"] >= 2

    # Restore using the returned map
    r2 = client.post("/v1/restore",
                     json={"text": body["sanitized_text"],
                           "placeholder_map": body["placeholder_map"]},
                     headers=AUTH)
    assert r2.status_code == 200
    assert r2.json()["restored_text"] == "Email me at jane@acme.com or SSN 123-45-6789"


def test_detect():
    client, _ = make_client()
    r = client.post("/v1/detect", json={"text": "card 4242 4242 4242 4242"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"].get("CREDIT_CARD") == 1
    assert body["detections"][0]["value"] == "4242 4242 4242 4242"

    # include_values=false omits the raw PII
    r2 = client.post("/v1/detect",
                     json={"text": "card 4242 4242 4242 4242", "include_values": False},
                     headers=AUTH)
    assert r2.json()["detections"][0]["value"] is None


def test_chat_completions_scrubs_then_restores():
    client, fake = make_client()
    r = client.post("/v1/chat/completions", json={
        "model": "test-model",
        "messages": [{"role": "user", "content": "Contact jane@acme.com please"}],
    }, headers=AUTH)
    assert r.status_code == 200
    # Upstream must have received SCRUBBED text — no raw email leaves the gateway
    sent = fake.chat.completions.last["messages"][-1]["content"]
    assert "jane@acme.com" not in sent
    assert "[EMAIL_1]" in sent
    # Response is restored for the caller
    body = r.json()
    assert "jane@acme.com" in body["choices"][0]["message"]["content"]
    assert body["x_preserve"]["pii_redacted"] == 1
    assert body["x_preserve"]["by_type"]["EMAIL"] == 1


def test_streaming_rejected():
    client, _ = make_client()
    r = client.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}], "stream": True,
    }, headers=AUTH)
    assert r.status_code == 400


def test_rate_limit():
    client, _ = make_client(rpm=1)
    assert client.post("/v1/scrub", json={"text": "a"}, headers=AUTH).status_code == 200
    r = client.post("/v1/scrub", json={"text": "b"}, headers=AUTH)
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_input_too_large():
    client, _ = make_client()
    settings = client.app.state.settings
    big = "x" * (settings.max_input_chars + 1)
    r = client.post("/v1/scrub", json={"text": big}, headers=AUTH)
    assert r.status_code == 413
