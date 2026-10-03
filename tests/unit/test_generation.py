"""Generation outcomes must not depend on optional webhook persistence."""

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.models.generation import GenerationRequest
from app.schemas.generate import ChatRequest
from app.schemas.response import LLMResponse
from app.services.generation import GenerationService


@pytest.mark.asyncio
async def test_webhook_error_preserves_success(test_session, test_api_key):
    api_key, _ = test_api_key
    response = LLMResponse(
        request_id="webhook-success",
        provider="openai",
        model="gpt-4o",
        content="Hello",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        finish_reason="stop",
        latency_ms=1,
    )
    provider = Mock(provider_name="openai", generate=AsyncMock(return_value=response))
    service = GenerationService(
        test_session, provider_factory=Mock(resolve=Mock(return_value=provider))
    )
    service.webhook_service.dispatch = AsyncMock(side_effect=RuntimeError("webhook DB failure"))
    request = ChatRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
        webhook_url="https://example.com/webhook",
    )

    assert await service.execute(request, api_key, response.request_id) == response
    records = (await test_session.execute(select(GenerationRequest))).scalars().all()
    assert len(records) == 1
    assert records[0].status == "success"


@pytest.mark.asyncio
async def test_webhook_error_preserves_provider_exception(test_session, test_api_key):
    api_key, _ = test_api_key
    failure = RuntimeError("provider unavailable")
    provider = Mock(provider_name="openai", generate=AsyncMock(side_effect=failure))
    service = GenerationService(
        test_session, provider_factory=Mock(resolve=Mock(return_value=provider))
    )
    service.webhook_service.dispatch = AsyncMock(side_effect=RuntimeError("webhook DB failure"))
    request = ChatRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
        webhook_url="https://example.com/webhook",
    )

    with pytest.raises(RuntimeError) as raised:
        await service.execute(request, api_key, "webhook-failure")
    assert raised.value is failure
    record = (await test_session.execute(select(GenerationRequest))).scalar_one()
    assert record.status == "failed"
    assert record.error_message == "provider unavailable"
