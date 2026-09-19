"""Integration tests for authentication and API key security."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import extract_key_prefix, generate_raw_api_key, hash_api_key
from app.models.api_key import ApiKey


@pytest.mark.asyncio
async def test_missing_api_key_rejected(async_client: httpx.AsyncClient) -> None:
    """Requests without authentication receive 401 Unauthorized with structured error."""
    response = await async_client.post(
        "/v1/generate",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "Missing API key" in data["error"]["message"]
    assert "request_id" in data["error"]


@pytest.mark.asyncio
async def test_invalid_api_key_rejected(async_client: httpx.AsyncClient) -> None:
    """Requests with non-existent API keys receive 401 Unauthorized."""
    response = await async_client.post(
        "/v1/generate",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        headers={"X-API-Key": "gw_live_nonexistentkey123456789"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "Invalid API key" in data["error"]["message"]


@pytest.mark.asyncio
async def test_deactivated_api_key_rejected(
    async_client: httpx.AsyncClient,
    test_session: AsyncSession,
) -> None:
    """Deactivated API keys are rejected with 401 Unauthorized."""
    raw_key = generate_raw_api_key()
    inactive_key = ApiKey(
        client_name="Deactivated Client",
        key_hash=hash_api_key(raw_key),
        key_prefix=extract_key_prefix(raw_key),
        is_active=False,
    )
    test_session.add(inactive_key)
    await test_session.commit()

    response = await async_client.post(
        "/v1/generate",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 401
    data = response.json()
    assert "deactivated" in data["error"]["message"]


@pytest.mark.asyncio
async def test_bearer_token_authorization(
    async_client: httpx.AsyncClient,
    test_api_key: tuple[ApiKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clients can authenticate using Authorization: Bearer <key>."""
    _, raw_key = test_api_key

    # Mock provider response
    from app.services import generation as gen_module

    old_init = gen_module.GenerationService.__init__

    async def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Bearer OK"}}],
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

    response = await async_client.post(
        "/v1/generate",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200
    assert response.json()["content"] == "Bearer OK"
