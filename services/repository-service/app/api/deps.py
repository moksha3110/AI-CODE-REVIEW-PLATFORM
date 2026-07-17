import secrets
from collections.abc import AsyncGenerator

from fastapi import Header
from redis.asyncio import Redis, from_url
from shared_auth import get_current_user_id, verifier_from_env

from app.core.config import get_settings
from app.core.exceptions import InternalAuthError

_redis: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)
    yield _redis


get_current_user_id_dep = get_current_user_id(verifier_from_env())


async def require_internal_service(x_internal_api_key: str | None = Header(default=None)) -> None:
    """
    Guards service-to-service routes (e.g. AI Analysis Service asking for an
    installation token). A shared static key is the pragmatic choice for
    this project's scope; in a stricter production setup this would be
    mTLS between pods or a service-mesh identity (e.g. SPIFFE/Istio) instead
    of a bearer secret.
    """
    settings = get_settings()
    if x_internal_api_key is None or not secrets.compare_digest(
        x_internal_api_key, settings.internal_service_api_key
    ):
        raise InternalAuthError("missing or invalid internal service credential")
