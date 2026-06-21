"""Tests for the PreserveClient (mocked API calls)."""

from unittest.mock import MagicMock, patch

import pytest

from preserve.client import PreserveClient, PreserveResponse
from preserve.config import PreserveConfig


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI chat completion response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "I've noted the email [EMAIL_1] and SSN [SSN_1]."
    response.model = "test-model"
    response.usage = MagicMock()
    response.usage.prompt_tokens = 50
    response.usage.completion_tokens = 20
    response.usage.total_tokens = 70
    return response


@pytest.fixture(scope="session")
def client():
    with patch("preserve.client.OpenAI"):
        return PreserveClient(
            api_key="test-key",
            model="test-model",
            base_url="https://test.api.com/v1",
        )


class TestPreserveClient:
    def test_scrub_only(self, client):
        messages = [{"role": "user", "content": "My email is john@example.com"}]
        sanitized, pm = client.scrub_only(messages)
        assert "john@example.com" not in sanitized[0]["content"]
        assert "[EMAIL_1]" in sanitized[0]["content"]
        assert pm.get_original("[EMAIL_1]") == "john@example.com"

    def test_chat_scrubs_and_restores(self, client, mock_openai_response):
        client._client.chat.completions.create.return_value = mock_openai_response

        messages = [
            {"role": "user", "content": "My email is john@example.com and SSN 123-45-6789"}
        ]
        response = client.chat(messages)

        # Verify the API was called with scrubbed content
        call_args = client._client.chat.completions.create.call_args
        sent_messages = call_args.kwargs["messages"]
        assert "john@example.com" not in sent_messages[0]["content"]
        assert "123-45-6789" not in sent_messages[0]["content"]

        # Verify response was restored
        assert isinstance(response, PreserveResponse)
        assert "john@example.com" in response.restored_response
        assert "123-45-6789" in response.restored_response

        # Raw response should still have placeholders
        assert "[EMAIL_1]" in response.raw_response

    def test_chat_without_scrub(self, client, mock_openai_response):
        mock_openai_response.choices[0].message.content = "Got it."
        client._client.chat.completions.create.return_value = mock_openai_response

        messages = [{"role": "user", "content": "My email is john@example.com"}]
        response = client.chat(messages, scrub=False)

        # API should be called with original content
        call_args = client._client.chat.completions.create.call_args
        sent_messages = call_args.kwargs["messages"]
        assert "john@example.com" in sent_messages[0]["content"]

    def test_audit_log_recorded(self, client, mock_openai_response):
        client._client.chat.completions.create.return_value = mock_openai_response

        initial_count = len(client.audit_log)
        messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
        client.chat(messages)

        assert len(client.audit_log) == initial_count + 1
        assert client.audit_log.total_pii_scrubbed >= 1

    def test_usage_tracking(self, client, mock_openai_response):
        client._client.chat.completions.create.return_value = mock_openai_response

        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert response.usage["total_tokens"] == 70

    def test_text_property(self, client, mock_openai_response):
        client._client.chat.completions.create.return_value = mock_openai_response

        messages = [{"role": "user", "content": "Email: a@b.com, SSN: 123-45-6789"}]
        response = client.chat(messages)
        # .text should be the de-anonymized version
        assert response.text == response.restored_response
