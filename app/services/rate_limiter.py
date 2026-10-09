"""Redis-backed distributed sliding-window rate limiter."""

import time
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.core.logging import get_logger

logger = get_logger("services.rate_limiter")


@dataclass(frozen=True)
class RateLimitResult:
    """Result of rate limit check with header metadata."""

    allowed: bool
    limit: int
    remaining: int
    reset_epoch: int
    degraded: bool = False

    @property
    def headers(self) -> dict[str, str]:
        """Convert rate limit status to standard HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }
        if self.degraded:
            headers["X-RateLimit-Degraded"] = "true"
        return headers


class RateLimiter:
    """Evaluates request rate limits using Redis with a deliberate failure policy."""

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client
        self.settings = get_settings()

    async def check_rate_limit(
        self,
        key_identifier: str,
        limit_override: int | None = None,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """Check whether key_identifier is within its rate limit window.

        Uses an atomic Redis pipeline with sorted sets to maintain a sliding window.
        """
        limit = (
            limit_override if limit_override is not None else self.settings.rate_limit_per_minute
        )
        now = time.time()
        clear_before = now - window_seconds
        redis_key = f"ratelimit:{key_identifier}"

        if limit < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")

        try:
            # WATCH makes the quota check and insertion a single optimistic
            # transaction. Concurrent callers retry instead of oversubscribing.
            for _ in range(20):
                async with self.redis.pipeline(transaction=True) as pipe:
                    try:
                        await pipe.watch(redis_key)
                        # Do not mutate the watched key before MULTI.
                        current_requests = await pipe.zcount(
                            redis_key, f"({clear_before}", "+inf"
                        )
                        entries = await pipe.zrangebyscore(
                            redis_key, f"({clear_before}", "+inf", start=0, num=1,
                            withscores=True,
                        )
                        reset_epoch = (
                            int(float(entries[0][1]) + window_seconds + 1)
                            if entries else int(now + window_seconds)
                        )
                        if current_requests >= limit:
                            await pipe.unwatch()
                            return RateLimitResult(
                                allowed=False, limit=limit, remaining=0,
                                reset_epoch=reset_epoch,
                            )

                        member = uuid.uuid4().hex
                        pipe.multi()
                        pipe.zremrangebyscore(redis_key, "-inf", clear_before)
                        pipe.zadd(redis_key, {member: now})
                        pipe.expire(redis_key, window_seconds + 1)
                        await pipe.execute()
                        return RateLimitResult(
                            allowed=True, limit=limit,
                            remaining=limit - current_requests - 1,
                            reset_epoch=reset_epoch,
                        )
                    except WatchError:
                        # Another request consumed quota while we were checking.
                        # Refresh the clock before retrying.
                        now = time.time()
                        clear_before = now - window_seconds
                        continue
            raise RedisError("rate limiter contention retry budget exhausted")

        except RedisError as exc:
            logger.error(
                "Redis rate limiter failure",
                key_identifier=key_identifier[:10] + "...",
                policy=self.settings.rate_limit_redis_failure_policy,
                error=str(exc),
            )

            if self.settings.rate_limit_redis_failure_policy == "fail_open":
                logger.warning(
                    "Redis unavailable; allowing request under fail_open policy",
                    key_identifier=key_identifier[:10] + "...",
                )
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=limit,
                    reset_epoch=int(now + window_seconds),
                    degraded=True,
                )
            else:
                logger.error(
                    "Redis unavailable; rejecting request under fail_closed policy",
                    key_identifier=key_identifier[:10] + "...",
                )
                raise RateLimitExceededError(
                    "Rate limit service is temporarily unavailable; request rejected "
                    "by fail-closed security policy."
                ) from exc
