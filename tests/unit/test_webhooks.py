"""Unit tests for HMAC webhook event generation and signature verification."""

import json

import httpx
import pytest

from app.core.security import compute_webhook_signature, verify_webhook_signature
from app.services.webhook import WebhookService


def test_webhook_signature_calculation() -> None:
    """HMAC-SHA256 signature is calculated over raw JSON payload bytes."""
    secret = "secret-key-32-bytes-long-here-ok"
    payload = {"hello": "world", "number": 42}
    raw_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    sig1 = compute_webhook_signature(raw_bytes, secret)
    sig2 = compute_webhook_signature(raw_bytes, secret)

    assert sig1 == sig2
    assert len(sig1) == 64
    assert verify_webhook_signature(raw_bytes, secret, sig1) is True


@pytest.mark.asyncio
async def test_webhook_dispatch_success() -> None:
    """WebhookService dispatches signed payload with correct HTTP headers."""
    received_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    service = WebhookService(http_client=client)
    success = await service.dispatch(
        webhook_url="https://client.example.com/events",
        request_id="req_webhook_123",
        event_type="generation.completed",
        payload={"content": "Model output", "tokens": 100},
    )

    assert success is True
    assert len(received_requests) == 1

    req = received_requests[0]
    assert req.headers["Content-Type"] == "application/json"
    assert "X-Webhook-Signature" in req.headers
    assert req.headers["X-Webhook-Signature"].startswith("v1=")
    assert req.headers["X-Request-ID"] == "req_webhook_123"

    body = json.loads(req.content.decode("utf-8"))
    assert body["request_id"] == "req_webhook_123"
    assert body["event_type"] == "generation.completed"
    assert body["payload"]["content"] == "Model output"


@pytest.mark.asyncio
async def test_webhook_dispatch_retry_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """WebhookService retries upon 500 error from client endpoint."""
    attempts = 0

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(500, text="Temporary error")
        return httpx.Response(200, text="Accepted")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)

    service = WebhookService(http_client=client)
    monkeypatch.setattr(service.settings, "webhook_max_retries", 3)

    success = await service.dispatch(
        webhook_url="https://client.example.com/events",
        request_id="req_webhook_retry",
        event_type="generation.completed",
        payload={"result": "done"},
    )

    assert success is True
    assert attempts == 2
