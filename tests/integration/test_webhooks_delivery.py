"""Integration tests for end-to-end webhook delivery and audit tracking."""

import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_webhook_signature
from app.models.api_key import ApiKey
from app.models.webhook import WebhookDelivery
from app.services import generation as gen_module


@pytest.mark.asyncio
async def test_end_to_end_webhook_delivery(
    async_client: httpx.AsyncClient,
    test_session: AsyncSession,
    test_api_key: tuple[ApiKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation request with webhook_url delivers a signed payload and logs audit state."""
    _, raw_key = test_api_key
    received_webhooks: list[dict] = []

    # Mock provider response and webhook destination
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "openai.com" in url_str:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "Async result"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )
        elif "client.example.com/callback" in url_str:
            received_webhooks.append(
                {
                    "headers": dict(request.headers),
                    "body": json.loads(request.content.decode("utf-8")),
                    "raw_content": request.content,
                }
            )
            return httpx.Response(200, text="OK")
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # Patch GenerationService to use mock client
    old_init = gen_module.GenerationService.__init__
    from app.providers.factory import ProviderFactory

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
        "messages": [{"role": "user", "content": "Generate something"}],
        "webhook_url": "https://client.example.com/callback",
    }

    response = await async_client.post(
        "/v1/generate",
        json=payload,
        headers={"X-API-Key": raw_key, "X-Request-ID": "req_hook_e2e"},
    )

    assert response.status_code == 200

    # Verify webhook was received by client endpoint
    assert len(received_webhooks) == 1
    webhook_data = received_webhooks[0]
    headers = webhook_data["headers"]
    body = webhook_data["body"]

    assert headers["x-request-id"] == "req_hook_e2e"
    assert "x-webhook-signature" in headers
    signature_header = headers["x-webhook-signature"]
    raw_sig = signature_header.replace("v1=", "")

    # Verify signature
    from app.core.config import get_settings

    secret = get_settings().webhook_secret
    assert verify_webhook_signature(webhook_data["raw_content"], secret, raw_sig) is True

    # Verify payload contents
    assert body["request_id"] == "req_hook_e2e"
    assert body["event_type"] == "generation.completed"
    assert body["payload"]["content"] == "Async result"

    # Verify database record in webhook_deliveries table
    stmt = select(WebhookDelivery).where(WebhookDelivery.request_id == "req_hook_e2e")
    result = await test_session.execute(stmt)
    delivery = result.scalar_one_or_none()

    assert delivery is not None
    assert delivery.status == "DELIVERED"
    assert delivery.attempts == 1
    assert delivery.last_attempt_at is not None
