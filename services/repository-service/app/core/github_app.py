"""
GitHub App authentication - completely separate credential chain from the
GitHub OAuth App in Auth Service.

The flow, per GitHub's docs:
  1. Sign a short-lived JWT (max 10 min) with the App's PRIVATE KEY, claiming
     to be App <github_app_id>.
  2. Exchange that JWT for an installation access token, scoped to exactly
     the repos one installation was granted - via
     POST /app/installations/{installation_id}/access_tokens.
  3. That installation token (valid ~1 hour) is what actually reads repo
     contents / receives webhooks for those repos.

Installation tokens are cached in Redis (a few minutes short of their real
TTL) so we're not minting a fresh token on every single webhook or clone -
GitHub does rate-limit this endpoint.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
import jwt as pyjwt
from redis.asyncio import Redis
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.core.exceptions import GitHubAPIError

GITHUB_API_BASE = "https://api.github.com"


def _is_retryable(exc: BaseException) -> bool:
    """Network errors and 5xx/429 are worth retrying; 4xx client errors
    (bad token, not found, etc.) never succeed on retry."""
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


@lru_cache
def _load_app_private_key() -> str:
    return Path(get_settings().github_app_private_key_path).read_text()


def _build_app_jwt() -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "iat": now - 30,  # small clock-skew buffer, per GitHub's recommendation
        "exp": now + 600,  # GitHub caps this JWT's lifetime at 10 minutes
        "iss": settings.github_app_id,
    }
    return pyjwt.encode(payload, _load_app_private_key(), algorithm="RS256")


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: int  # unix timestamp


@_retryable
async def _mint_installation_token(installation_id: int) -> InstallationToken:
    app_jwt = _build_app_jwt()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if resp.status_code == 404:
            raise GitHubAPIError(f"installation {installation_id} not found or app was uninstalled")
        resp.raise_for_status()
        payload = resp.json()

    # GitHub returns an ISO8601 expires_at; convert once here so callers deal in unix time.
    from datetime import datetime

    expires_dt = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    return InstallationToken(token=payload["token"], expires_at=int(expires_dt.timestamp()))


async def get_installation_token(redis: Redis, installation_id: int) -> str:
    """
    Returns a valid installation access token, serving from Redis cache when
    possible. This is the single choke point every caller (webhook handler,
    internal token endpoint) goes through, so GitHub's rate limit on token
    minting is respected regardless of how many services/replicas ask.
    """
    settings = get_settings()
    cache_key = f"gh_install_token:{installation_id}"

    cached = await redis.get(cache_key)
    if cached:
        return cached

    minted = await _mint_installation_token(installation_id)
    await redis.setex(cache_key, settings.installation_token_cache_ttl_seconds, minted.token)
    return minted.token


@_retryable
async def fetch_installation_repositories(token: str) -> list[dict]:
    """Lists the repos an installation was granted access to - used right
    after install to populate our `repositories` table."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/installation/repositories",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        return resp.json().get("repositories", [])


@_retryable
async def fetch_installation_info(installation_id: int) -> dict:
    """Fetches installation metadata (account login/type) directly with the
    App-level JWT - used once at install time, before we have a cached
    installation token worth reusing for this specific call."""
    app_jwt = _build_app_jwt()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/app/installations/{installation_id}",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if resp.status_code == 404:
            raise GitHubAPIError(f"installation {installation_id} not found")
        resp.raise_for_status()
        return resp.json()
