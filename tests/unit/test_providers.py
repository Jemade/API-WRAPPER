"""Unit tests for provider adapters and ProviderFactory routing."""

import json

import httpx
import pytest

from app.core.exceptions import (
    InvalidRequestError,
    ProviderConfigurationError,
    UpstreamBadRequestError,
)
from app.providers.anthropic import AnthropicProvider
from app.providers.factory import ProviderFactory
from app.providers.openai import OpenAIProvider
from app.schemas.generate import ChatMessage, ChatRequest


def test_provider_factory_routing() -> None:
    """Factory resolves models to the correct provider adapter based on prefix."""
    factory = ProviderFactory()

    openai_prov = factory.resolve("gpt-4o")
    assert isinstance(openai_prov, OpenAIProvider)
    assert openai_prov.provider_name == "openai"

    o1_prov = factory.resolve("o1-preview")
    assert isinstance(o1_prov, OpenAIProvider)

    anthropic_prov = factory.resolve("claude-3-5-sonnet-20241022")
    assert isinstance(anthropic_prov, AnthropicProvider)
    assert anthropic_prov.provider_name == "anthropic"

    with pytest.raises(InvalidRequestError) as exc_info:
        factory.resolve("unsupported-llm-v1")
    assert "Unsupported model" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openai_provider_success() -> None:
    """OpenAIProvider successfully normalizes a 200 OK Chat Completions response."""
    mock_response_payload = {
        "id": "chatcmpl-123",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from OpenAI!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "gpt-4o"
        return httpx.Response(200, json=mock_response_payload)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    chat_req = ChatRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hi")],
    )

    response = await provider.generate(chat_req, request_id="req_test123")
    assert response.request_id == "req_test123"
    assert response.provider == "openai"
    assert response.model == "gpt-4o"
    assert response.content == "Hello from OpenAI!"
    assert response.input_tokens == 12
    assert response.output_tokens == 8
    assert response.total_tokens == 20
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_anthropic_provider_success() -> None:
    """AnthropicProvider separates system messages and normalizes response content blocks."""
    mock_response_payload = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from Claude!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 15, "output_tokens": 10},
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "x-api-key" in request.headers
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "claude-3-5-sonnet-20241022"
        # Verify system prompt extraction
        assert body["system"] == "You are a helpful assistant."
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(200, json=mock_response_payload)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = AnthropicProvider(http_client=client)
    chat_req = ChatRequest(
        model="claude-3-5-sonnet-20241022",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Hi Claude"),
        ],
    )

    response = await provider.generate(chat_req, request_id="req_test_claude")
    assert response.request_id == "req_test_claude"
    assert response.provider == "anthropic"
    assert response.content == "Hello from Claude!"
    assert response.input_tokens == 15
    assert response.output_tokens == 10
    assert response.total_tokens == 25
    assert response.finish_reason == "end_turn"


@pytest.mark.asyncio
async def test_provider_400_bad_request() -> None:
    """Upstream 400 Bad Request raises UpstreamBadRequestError without retries."""

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error": {"message": "Invalid prompt length"}}')

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    chat_req = ChatRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Hi")])

    with pytest.raises(UpstreamBadRequestError) as exc_info:
        await provider.generate(chat_req, request_id="req_bad")
    assert "Invalid prompt length" in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_401_auth_error() -> None:
    """Upstream 401 Unauthorized raises ProviderConfigurationError without retries."""

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"error": {"message": "Incorrect API key"}}')

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    chat_req = ChatRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Hi")])

    with pytest.raises(ProviderConfigurationError) as exc_info:
        await provider.generate(chat_req, request_id="req_unauth")
    assert "rejected credentials" in str(exc_info.value)
