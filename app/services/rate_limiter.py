"""Redis-backed distributed sliding-window rate limiter."""

import random
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

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

        try:
            # 1. Clean old entries and count current requests in sliding window
            pipe = self.redis.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, "-inf", clear_before)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            results = await pipe.execute()

            current_requests = int(results[1])
            oldest_entries = results[2]

            if current_requests < limit:
                # Member unique string: timestamp:random_salt
                member = f"{now}:{random.randint(10000, 99999)}"
                add_pipe = self.redis.pipeline(transaction=True)
                add_pipe.zadd(redis_key, {member: now})
                add_pipe.expire(redis_key, int(window_seconds) + 1)
                await add_pipe.execute()

                remaining = limit - current_requests - 1
                reset_epoch = int(now + window_seconds)
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_epoch=reset_epoch,
                    degraded=False,
                )
            else:
                # Estimate reset epoch based on oldest entry in window
                reset_epoch = int(now + window_seconds)
                if oldest_entries and len(oldest_entries) > 0:
                    oldest_score = float(oldest_entries[0][1])
                    reset_epoch = int(oldest_score + window_seconds)

                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_epoch=reset_epoch,
                    degraded=False,
                )

        except RedisError as exc:
            logger.error(
                "Redis rate limiter failure",
                key_identifier=key_identifier[:10] + "...",
                policy=self.settings.rate_limit_redis_failure_policy,
                error=str(exc),
            )

            # Deliberate failure policy handling
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
