"""
Handles GitHub OAuth App login (the user-facing "sign in with GitHub").

This is intentionally separate from the GitHub App used by the Repository
Service for webhook/repo access - two different GitHub integration types
solving two different problems:

  - OAuth App (here): "who is this human logging into our platform"
  - GitHub App (Repository Service): "which repos can we read, and can we
    receive webhooks for them" - fine-grained, installable per-repo,
    revocable independently of any user's login session.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.core.exceptions import GitHubAPIError

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def _is_retryable(exc: BaseException) -> bool:
    """Network errors and 5xx/429 are worth retrying; 4xx client errors
    (bad/expired code, bad token, etc.) never succeed on retry."""
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


@dataclass(frozen=True)
class GitHubProfile:
    github_id: int
    login: str
    email: str | None
    avatar_url: str | None


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": settings.github_oauth_scope,
        "state": state,
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def generate_state() -> str:
    return secrets.token_urlsafe(32)


@_retryable
async def exchange_code_for_token(code: str) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    if "access_token" not in payload:
        raise GitHubAPIError(f"github token exchange failed: {payload.get('error_description', payload)}")

    return payload["access_token"]


@_retryable
async def fetch_github_profile(github_access_token: str) -> GitHubProfile:
    headers = {
        "Authorization": f"Bearer {github_access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            user_resp = await client.get(GITHUB_USER_URL, headers=headers)
            user_resp.raise_for_status()
            user = user_resp.json()

            email = user.get("email")
            if not email:
                # Primary email is often private; fall back to the emails endpoint.
                emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    primary = next((e for e in emails if e.get("primary")), None)
                    email = primary["email"] if primary else None
    except httpx.HTTPStatusError as exc:
        raise GitHubAPIError(f"github profile fetch failed: {exc.response.status_code}") from exc

    return GitHubProfile(
        github_id=user["id"],
        login=user["login"],
        email=email,
        avatar_url=user.get("avatar_url"),
    )
