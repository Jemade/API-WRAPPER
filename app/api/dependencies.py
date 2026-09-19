"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator

from fastapi import Depends, Header
from redis.asyncio import Redis, from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.services.rate_limiter import RateLimiter

_redis_client: Redis | None = None


async def get_redis(settings: Settings = Depends(get_settings)) -> AsyncGenerator[Redis, None]:
    """Provide an async Redis client from the shared connection pool."""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    yield _redis_client


def get_rate_limiter(redis_client: Redis = Depends(get_redis)) -> RateLimiter:
    """Provide a RateLimiter service instance."""
    return RateLimiter(redis_client=redis_client)


async def get_current_client(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """Authenticate the client via X-API-Key header or Bearer token."""
    raw_key: str | None = None

    if x_api_key:
        raw_key = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        raw_key = authorization[7:].strip()

    if not raw_key:
        raise UnauthorizedError(
            "Missing API key. Provide authentication via 'X-API-Key' header "
            "or 'Authorization: Bearer <key>'."
        )

    # Compute deterministic SHA-256 hash for lookup
    key_hash = hash_api_key(raw_key)

    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await db.execute(stmt)
    client = result.scalar_one_or_none()

    if client is None:
        raise UnauthorizedError("Invalid API key.")

    if not client.is_active:
        raise UnauthorizedError("API key has been deactivated or revoked.")

    return client
