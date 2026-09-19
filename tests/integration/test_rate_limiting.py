"""Integration tests for rate limiting enforcement at API level."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import extract_key_prefix, generate_raw_api_key, hash_api_key
from app.models.api_key import ApiKey


@pytest.mark.asyncio
async def test_api_rate_limiting_enforcement(
    async_client: httpx.AsyncClient,
    test_session: AsyncSession,
    test_api_key: tuple[ApiKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clients hitting rate limits receive 429 Too Many Requests and Retry-After header."""
    _, raw_key = test_api_key

    # Mock provider response
    from app.services import generation as gen_module

    old_init = gen_module.GenerationService.__init__

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    from app.providers.factory import ProviderFactory

    factory = ProviderFactory(http_client=mock_client)
    monkeypatch.setattr(
        gen_module.GenerationService,
        "__init__",
        lambda self, db_session, http_client=None, provider_factory=None: old_init(
            self, db_session=db_session, http_client=mock_client, provider_factory=factory
        ),
    )

    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}
    headers = {"X-API-Key": raw_key}

    # Test key has limit of 5 req/min
    for i in range(5):
        resp = await async_client.post("/v1/generate", json=payload, headers=headers)
        assert resp.status_code == 200, f"Request {i + 1} failed"
        assert int(resp.headers["X-RateLimit-Remaining"]) == 4 - i

    # 6th request must be rejected with 429
    resp_rate_limited = await async_client.post("/v1/generate", json=payload, headers=headers)
    assert resp_rate_limited.status_code == 429
    assert "Retry-After" in resp_rate_limited.headers

    data = resp_rate_limited.json()
    assert data["error"]["code"] == "RATE_LIMITED"
    assert "exceeded" in data["error"]["message"].lower()

    # Create a second client to verify rate-limit isolation
    raw_key_2 = generate_raw_api_key()
    client_2 = ApiKey(
        client_name="Second Client",
        key_hash=hash_api_key(raw_key_2),
        key_prefix=extract_key_prefix(raw_key_2),
        is_active=True,
        rate_limit_per_minute=5,
    )
    test_session.add(client_2)
    await test_session.commit()

    resp_client_2 = await async_client.post(
        "/v1/generate",
        json=payload,
        headers={"X-API-Key": raw_key_2},
    )
    assert resp_client_2.status_code == 200
    assert resp_client_2.headers["X-RateLimit-Remaining"] == "4"
