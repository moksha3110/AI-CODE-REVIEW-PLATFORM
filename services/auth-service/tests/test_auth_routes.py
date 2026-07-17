import re

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.asyncio


async def test_liveness(client):
    resp = await client.get("/api/v1/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readiness(client):
    resp = await client.get("/api/v1/readyz")
    assert resp.status_code == 200


async def test_github_login_redirects_with_state(client):
    resp = await client.get("/api/v1/auth/github/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize")
    assert "state=" in location


async def test_github_login_rate_limited_after_threshold(client):
    # login_rate_limit_per_minute defaults to 10 in Settings
    for _ in range(10):
        resp = await client.get("/api/v1/auth/github/login", follow_redirects=False)
        assert resp.status_code in (302, 307)

    resp = await client.get("/api/v1/auth/github/login", follow_redirects=False)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limit_exceeded"


async def test_github_callback_rejects_unknown_state(client):
    resp = await client.get(
        "/api/v1/auth/github/callback",
        params={"code": "irrelevant", "state": "never-issued"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_oauth_state"


@respx.mock
async def test_github_callback_creates_user_and_issues_tokens(client):
    login_resp = await client.get("/api/v1/auth/github/login", follow_redirects=False)
    state = re.search(r"state=([^&]+)", login_resp.headers["location"]).group(1)

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=Response(200, json={"access_token": "gh-token-abc", "token_type": "bearer"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={"id": 42, "login": "octocat", "email": "octocat@example.com", "avatar_url": "https://x/y.png"},
        )
    )

    resp = await client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "access_token=" in resp.headers["location"]
    assert "refresh_token" in resp.cookies


@respx.mock
async def test_refresh_token_rotation_and_reuse_detection(client):
    login_resp = await client.get("/api/v1/auth/github/login", follow_redirects=False)
    state = re.search(r"state=([^&]+)", login_resp.headers["location"]).group(1)

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=Response(200, json={"access_token": "gh-token-abc"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=Response(200, json={"id": 7, "login": "hubot", "email": "hubot@example.com"})
    )

    callback_resp = await client.get(
        "/api/v1/auth/github/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )
    first_refresh_token = callback_resp.cookies["refresh_token"]
    client.cookies.set("refresh_token", first_refresh_token)

    # First refresh: should succeed and rotate to a new token.
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    new_refresh_token = refresh_resp.cookies["refresh_token"]
    assert new_refresh_token != first_refresh_token

    # Replaying the OLD (already-rotated) refresh token is theft-shaped
    # behavior - it must be rejected AND revoke the whole session family.
    client.cookies.set("refresh_token", first_refresh_token)
    reuse_resp = await client.post("/api/v1/auth/refresh")
    assert reuse_resp.status_code == 401
    assert reuse_resp.json()["error"]["code"] == "token_reuse_detected"

    # Because the family was revoked, even the NEW token (issued from that
    # same family) must now be rejected too.
    client.cookies.set("refresh_token", new_refresh_token)
    after_revoke_resp = await client.post("/api/v1/auth/refresh")
    assert after_revoke_resp.status_code == 401
