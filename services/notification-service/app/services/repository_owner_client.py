"""
Resolves which platform user owns a repository, via Repository Service's
internal API - this service never stores or reasons about Installations
itself, it just needs to know who to notify.
"""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.core.exceptions import OwnerLookupError


def _is_retryable(exc: BaseException) -> bool:
    """Network errors and 5xx/429 are worth retrying; 4xx client errors
    (bad internal API key, unknown repository) never succeed on retry."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


_retryable = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=4),
    retry=retry_if_exception(_is_retryable),
)


@_retryable
async def get_repository_owner(repository_id: str) -> str:
    settings = get_settings()
    url = f"{settings.repository_service_base_url}/api/v1/internal/repositories/{repository_id}/owner"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url, headers={"X-Internal-Api-Key": settings.internal_service_api_key}
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OwnerLookupError(
            f"repository-service returned {exc.response.status_code} for repository {repository_id}"
        ) from exc

    return resp.json()["user_id"]
