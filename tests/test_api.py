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


def test_chat_completions_restores_tool_call_args():
    client, fake = make_client()

    def fake_create(model, messages, **kw):
        # Upstream returns a tool call whose arguments reference the placeholder.
        return types.SimpleNamespace(model_dump=lambda: {
            "id": "chatcmpl-tc", "model": model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "send_email", "arguments": '{"to": "[EMAIL_1]"}'}}],
            }}],
            "usage": {"total_tokens": 10},
        })
    fake.chat.completions.create = fake_create

    r = client.post("/v1/chat/completions", json={
        "model": "test-model",
        "messages": [{"role": "user", "content": "Email jane@acme.com about the invoice"}],
    }, headers=AUTH)
    assert r.status_code == 200
    args = r.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    assert "jane@acme.com" in args and "[EMAIL_1]" not in args


def test_streaming_restores_split_placeholder():
    client, fake = make_client()

    def fake_create(model, messages, stream=False, **kw):
        assert stream is True
        # The placeholder [EMAIL_1] is split across fragments.
        frags = ["Sure, ", "I'll write to [EMA", "IL_1]", " now."]

        def gen():
            for fr in frags:
                yield types.SimpleNamespace(model_dump=lambda fr=fr: {
                    "id": "chatcmpl-s", "object": "chat.completion.chunk", "model": model,
                    "choices": [{"index": 0, "delta": {"content": fr}, "finish_reason": None}],
                })
        return gen()
    fake.chat.completions.create = fake_create

    r = client.post("/v1/chat/completions", json={
        "model": "test-model", "stream": True,
        "messages": [{"role": "user", "content": "Email jane@acme.com about it"}],
    }, headers=AUTH)
    assert r.status_code == 200
    body = r.text

    content = ""
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload == "[DONE]":
                continue
            obj = __import__("json").loads(payload)
            for ch in obj.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if c:
                    content += c
    # Upstream got scrubbed text; client gets restored, never a partial/placeholder
    assert content == "Sure, I'll write to jane@acme.com now."
    assert "[EMAIL_1]" not in body and "[EMA" not in body
    assert body.strip().endswith("data: [DONE]")


def test_anthropic_messages_scrubs_and_restores():
    client, fake = make_client()
    r = client.post("/v1/messages", json={
        "model": "test-model", "max_tokens": 100,
        "system": "You are a helpful assistant.",
        "messages": [{"role": "user", "content": "Contact jane@acme.com please"}],
    }, headers=AUTH)
    assert r.status_code == 200
    sent = fake.chat.completions.last["messages"]
    assert any(m["role"] == "system" for m in sent)
    user_sent = [m for m in sent if m["role"] == "user"][-1]["content"]
    assert "jane@acme.com" not in user_sent and "[EMAIL_1]" in user_sent
    body = r.json()
    assert body["type"] == "message" and body["role"] == "assistant"
    assert body["content"][0]["type"] == "text"
    assert "jane@acme.com" in body["content"][0]["text"]
    assert "input_tokens" in body["usage"] and "output_tokens" in body["usage"]
    assert body["x_preserve"]["by_type"]["EMAIL"] == 1


def test_anthropic_messages_content_blocks():
    client, fake = make_client()
    r = client.post("/v1/messages", json={
        "model": "test-model", "max_tokens": 50,
        "messages": [{"role": "user",
                      "content": [{"type": "text", "text": "SSN 123-45-6789 ok"}]}],
    }, headers=AUTH)
    assert r.status_code == 200
    user_sent = [m for m in fake.chat.completions.last["messages"]
                 if m["role"] == "user"][-1]["content"]
    assert "123-45-6789" not in user_sent and "[SSN_1]" in user_sent


def test_anthropic_messages_streaming_restores():
    client, fake = make_client()

    def fake_create(model, messages, stream=False, **kw):
        assert stream is True
        frags = ["Sure, ", "writing to [EMA", "IL_1]", " now."]

        def gen():
            for fr in frags:
                yield types.SimpleNamespace(model_dump=lambda fr=fr: {
                    "choices": [{"index": 0, "delta": {"content": fr}, "finish_reason": None}]})
        return gen()
    fake.chat.completions.create = fake_create

    r = client.post("/v1/messages", json={
        "model": "test-model", "stream": True,
        "messages": [{"role": "user", "content": "Email jane@acme.com about it"}],
    }, headers=AUTH)
    assert r.status_code == 200
    body = r.text
    assert "event: message_start" in body and "event: message_stop" in body
    text = ""
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                obj = __import__("json").loads(line[6:])
            except Exception:
                continue
            if obj.get("type") == "content_block_delta" and obj["delta"].get("type") == "text_delta":
                text += obj["delta"]["text"]
    assert text == "Sure, writing to jane@acme.com now."
    assert "[EMAIL_1]" not in body and "[EMA" not in body


def test_anthropic_messages_tool_use_restored():
    client, fake = make_client()

    def fake_create(model, messages, **kw):
        return types.SimpleNamespace(model_dump=lambda: {
            "id": "msg-x", "model": model,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "send_email", "arguments": '{"to": "[EMAIL_1]"}'}}]}}],
            "usage": {"total_tokens": 10}})
    fake.chat.completions.create = fake_create

    r = client.post("/v1/messages", json={
        "model": "test-model",
        "messages": [{"role": "user", "content": "Email jane@acme.com"}],
    }, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    tool_blocks = [b for b in body["content"] if b["type"] == "tool_use"]
    assert tool_blocks and tool_blocks[0]["name"] == "send_email"
    assert tool_blocks[0]["input"] == {"to": "jane@acme.com"}
    assert body["stop_reason"] == "tool_use"


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


def test_rate_limiter_factory_falls_back_to_memory(monkeypatch):
    # No REDIS_URL -> in-memory limiter
    from preserve.api.ratelimit import RateLimiter, get_rate_limiter
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert isinstance(get_rate_limiter(), RateLimiter)
    # Unreachable REDIS_URL -> still falls back (no crash)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390/0")
    assert isinstance(get_rate_limiter(), RateLimiter)
