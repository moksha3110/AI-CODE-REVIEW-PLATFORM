"""
Fixed-window rate limiting backed by Redis, applied to auth-sensitive
endpoints (login, callback) to blunt credential-stuffing / OAuth-abuse
attempts. Kept as a FastAPI dependency (not global middleware) so each
route can opt into its own limit and key strategy.
"""
from redis.asyncio import Redis

from app.core.exceptions import RateLimitExceededError


def rate_limiter(redis: Redis, limit: int, window_seconds: int = 60):
    async def _check(key: str) -> None:
        bucket_key = f"ratelimit:{key}"
        current = await redis.incr(bucket_key)
        if current == 1:
            await redis.expire(bucket_key, window_seconds)
        if current > limit:
            raise RateLimitExceededError(
                f"rate limit exceeded: max {limit} requests per {window_seconds}s"
            )

    return _check
