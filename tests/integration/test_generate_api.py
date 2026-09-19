"""Integration tests for the POST /v1/generate endpoint."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.generation import GenerationRequest
from app.providers.factory import ProviderFactory


@pytest.mark.asyncio
async def test_successful_generate_flow(
    async_client: httpx.AsyncClient,
    test_session: AsyncSession,
    test_api_key: tuple[ApiKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full lifecycle: authenticated request forwarded to provider, audited in DB."""
    _, raw_key = test_api_key

    # Mock upstream OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "The capital of France is Paris."},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18,
        },
    }

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_openai_response)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    from app.services import generation as gen_module

    old_init = gen_module.GenerationService.__init__
    factory = ProviderFactory(http_client=mock_client)

    monkeypatch.setattr(
        gen_module.GenerationService,
        "__init__",
        lambda self, db_session, http_client=None, provider_factory=None: old_init(
            self, db_session=db_session, http_client=mock_client, provider_factory=factory
        ),
    )

    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
        "temperature": 0.5,
        "max_tokens": 100,
    }

    response = await async_client.post(
        "/v1/generate",
        json=payload,
        headers={"X-API-Key": raw_key, "X-Request-ID": "custom-trace-id-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "custom-trace-id-123"
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers

    data = response.json()
    assert data["request_id"] == "custom-trace-id-123"
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"
    assert data["content"] == "The capital of France is Paris."
    assert data["input_tokens"] == 10
    assert data["output_tokens"] == 8
    assert data["total_tokens"] == 18
    assert data["finish_reason"] == "stop"
    assert data["latency_ms"] >= 0.0

    # Verify audit record persisted in database
    stmt = select(GenerationRequest).where(GenerationRequest.id == "custom-trace-id-123")
    result = await test_session.execute(stmt)
    audit = result.scalar_one_or_none()

    assert audit is not None
    assert audit.status == "success"
    assert audit.provider == "openai"
    assert audit.total_tokens == 18
