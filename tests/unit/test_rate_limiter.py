"""Unit tests for the Redis sliding-window rate limiter."""

import asyncio

import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.exceptions import RateLimitExceededError
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_below_limit(test_redis: FakeRedis) -> None:
    """Requests below quota are allowed and remaining quota decrements."""
    limiter = RateLimiter(redis_client=test_redis)
    key = "client_key_1"

    res1 = await limiter.check_rate_limit(key, limit_override=3, window_seconds=60)
    assert res1.allowed is True
    assert res1.remaining == 2
    assert res1.limit == 3

    res2 = await limiter.check_rate_limit(key, limit_override=3, window_seconds=60)
    assert res2.allowed is True
    assert res2.remaining == 1

    res3 = await limiter.check_rate_limit(key, limit_override=3, window_seconds=60)
    assert res3.allowed is True
    assert res3.remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_above_limit(test_redis: FakeRedis) -> None:
    """Requests exceeding the limit are rejected with allowed=False and remaining=0."""
    limiter = RateLimiter(redis_client=test_redis)
    key = "client_key_2"

    # Consume all 2 slots
    await limiter.check_rate_limit(key, limit_override=2, window_seconds=60)
    await limiter.check_rate_limit(key, limit_override=2, window_seconds=60)

    # Third request is blocked
    res_blocked = await limiter.check_rate_limit(key, limit_override=2, window_seconds=60)
    assert res_blocked.allowed is False
    assert res_blocked.remaining == 0
    assert res_blocked.reset_epoch > 0


@pytest.mark.asyncio
async def test_rate_limiter_different_keys_isolated(test_redis: FakeRedis) -> None:
    """Rate limits for distinct API keys do not affect each other."""
    limiter = RateLimiter(redis_client=test_redis)
    key_a = "client_a"
    key_b = "client_b"

    # Exhaust key_a
    await limiter.check_rate_limit(key_a, limit_override=1, window_seconds=60)
    res_a_blocked = await limiter.check_rate_limit(key_a, limit_override=1, window_seconds=60)
    assert res_a_blocked.allowed is False

    # key_b remains unaffected
    res_b = await limiter.check_rate_limit(key_b, limit_override=1, window_seconds=60)
    assert res_b.allowed is True
    assert res_b.remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_window_expiry(test_redis: FakeRedis) -> None:
    """After the sliding window expires, quota is fully restored."""
    limiter = RateLimiter(redis_client=test_redis)
    key = "client_window_test"

    # Limit = 1 with a short 1-second window
    res1 = await limiter.check_rate_limit(key, limit_override=1, window_seconds=1)
    assert res1.allowed is True

    # Immediate second request is blocked
    res2 = await limiter.check_rate_limit(key, limit_override=1, window_seconds=1)
    assert res2.allowed is False

    # Wait for the window to slide past
    await asyncio.sleep(1.1)

    # Quota is restored
    res3 = await limiter.check_rate_limit(key, limit_override=1, window_seconds=1)
    assert res3.allowed is True
    assert res3.remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_redis_failure_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Redis fails and policy is 'fail_open', request is allowed with degraded=True."""

    class BrokenRedis:
        def pipeline(self, *args, **kwargs):
            raise RedisConnectionError("Redis cluster unreachable")

    limiter = RateLimiter(redis_client=BrokenRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(limiter.settings, "rate_limit_redis_failure_policy", "fail_open")

    res = await limiter.check_rate_limit("client_broken", limit_override=10)
    assert res.allowed is True
    assert res.degraded is True
    assert "X-RateLimit-Degraded" in res.headers


@pytest.mark.asyncio
async def test_rate_limiter_redis_failure_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Redis fails and policy is 'fail_closed', RateLimitExceededError is raised."""

    class BrokenRedis:
        def pipeline(self, *args, **kwargs):
            raise RedisConnectionError("Redis cluster unreachable")

    limiter = RateLimiter(redis_client=BrokenRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(limiter.settings, "rate_limit_redis_failure_policy", "fail_closed")

    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check_rate_limit("client_broken", limit_override=10)
    assert "fail-closed" in str(exc_info.value)
