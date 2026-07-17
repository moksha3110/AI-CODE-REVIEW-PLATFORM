from collections.abc import AsyncGenerator

from redis.asyncio import Redis, from_url
from shared_auth import get_current_user_id, verifier_from_env

from app.core.config import get_settings

_redis: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)
    yield _redis


# Auth Service protects its own routes (e.g. /auth/me) the exact same way
# every other service will - proof that the shared library is a real
# contract, not just documentation.
get_current_user_id_dep = get_current_user_id(verifier_from_env())
