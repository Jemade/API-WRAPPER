"""Unit tests for tenacity retry behaviors on transient vs permanent errors."""

import httpx
import pytest

from app.core.exceptions import (
    InvalidRequestError,
    ProviderConfigurationError,
    UpstreamBadRequestError,
    UpstreamUnavailableError,
)
from app.providers.base import UpstreamTransientError, is_transient_error
from app.providers.openai import OpenAIProvider
from app.schemas.generate import ChatMessage, ChatRequest


def test_transient_error_classification() -> None:
    """Validate exception types that qualify for retry vs immediate failure."""
    assert is_transient_error(httpx.ConnectTimeout("timeout")) is True
    assert is_transient_error(httpx.ReadTimeout("timeout")) is True
    assert is_transient_error(httpx.NetworkError("connection reset")) is True
    assert is_transient_error(UpstreamTransientError("503 Service Unavailable")) is True

    # Non-transient errors must NOT be retried
    assert is_transient_error(UpstreamBadRequestError("400 Bad Request")) is False
    assert is_transient_error(ProviderConfigurationError("401 Unauthorized")) is False
    assert is_transient_error(InvalidRequestError("Invalid model")) is False
    assert is_transient_error(ValueError("Invalid argument")) is False


@pytest.mark.asyncio
async def test_retry_on_transient_503_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider retries through transient 503 errors and succeeds when upstream recovers."""
    attempts = 0

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="Overloaded")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Recovered!"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    # Fast backoff for tests
    monkeypatch.setattr(provider.settings, "retry_backoff_factor", 0.01)
    monkeypatch.setattr(provider.settings, "max_retries", 3)

    req = ChatRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Hi")])
    res = await provider.generate(req, request_id="req_retry_test")

    assert attempts == 3
    assert res.content == "Recovered!"


@pytest.mark.asyncio
async def test_retry_exhaustion_raises_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider exhausts configured max_retries and raises UpstreamUnavailableError."""
    attempts = 0

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    monkeypatch.setattr(provider.settings, "retry_backoff_factor", 0.01)
    monkeypatch.setattr(provider.settings, "max_retries", 2)

    req = ChatRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Hi")])
    with pytest.raises(UpstreamUnavailableError) as exc_info:
        await provider.generate(req, request_id="req_exhaust")

    assert attempts == 2
    assert "unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_no_retry_on_bad_request() -> None:
    """400 Bad Request terminates immediately without retrying."""
    attempts = 0

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, text="Invalid parameters")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    provider = OpenAIProvider(http_client=client)
    req = ChatRequest(model="gpt-4o", messages=[ChatMessage(role="user", content="Hi")])

    with pytest.raises(UpstreamBadRequestError):
        await provider.generate(req, request_id="req_no_retry")

    assert attempts == 1
