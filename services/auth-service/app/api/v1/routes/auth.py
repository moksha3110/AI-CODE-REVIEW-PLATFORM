from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id_dep, get_redis
from app.core import security
from app.core.config import get_settings
from app.core.exceptions import AppError, InvalidOAuthStateError, InvalidTokenError
from app.core.logging import get_logger
from app.db.session import get_db
from app.middleware.rate_limit import rate_limiter
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import AccessTokenOnly, RefreshRequest
from app.schemas.user import UserOut
from app.services import github_oauth, token_service
from app.services.token_service import hash_jti

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)

REFRESH_COOKIE_NAME = "refresh_token"


def _refresh_cookie_kwargs() -> dict:
    settings = get_settings()
    return dict(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.env != "local",
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )


@router.get("/github/login")
async def github_login(request: Request, redis: Redis = Depends(get_redis)):
    """
    Redirects the browser to GitHub's OAuth consent screen. The `state`
    parameter is stored in Redis with a short TTL and re-checked on
    callback - this is the CSRF protection for the OAuth flow.
    """
    settings = get_settings()
    limiter = rate_limiter(redis, settings.login_rate_limit_per_minute)
    client_ip = request.client.host if request.client else "unknown"
    await limiter(f"github_login:{client_ip}")

    state = github_oauth.generate_state()
    await redis.setex(f"oauth_state:{state}", settings.oauth_state_ttl_seconds, "1")

    return RedirectResponse(github_oauth.build_authorize_url(state))


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    GitHub redirects here after the user approves (or denies) access.
    On success: upsert the user, issue our own access+refresh token pair,
    set the refresh token as an httpOnly cookie, and redirect the browser
    back to the frontend with the access token as a URL fragment (never a
    query param - fragments aren't sent to the server or logged).
    """
    settings = get_settings()

    state_key = f"oauth_state:{state}"
    if not await redis.get(state_key):
        raise InvalidOAuthStateError("oauth state missing, expired, or already used")
    await redis.delete(state_key)

    github_token = await github_oauth.exchange_code_for_token(code)
    profile = await github_oauth.fetch_github_profile(github_token)

    result = await db.execute(select(User).where(User.github_id == profile.github_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            github_id=profile.github_id,
            github_login=profile.login,
            email=profile.email,
            avatar_url=profile.avatar_url,
        )
        db.add(user)
        logger.info("user_created", github_login=profile.login)
    else:
        user.github_login = profile.login
        user.email = profile.email
        user.avatar_url = profile.avatar_url

    await db.commit()
    await db.refresh(user)

    tokens = await token_service.issue_token_pair(db, user.id)

    redirect = RedirectResponse(
        url=f"{settings.frontend_url}{settings.frontend_auth_callback_path}#access_token={tokens['access_token']}"
    )
    redirect.set_cookie(value=tokens["refresh_token"], **_refresh_cookie_kwargs())
    return redirect


@router.post("/refresh", response_model=AccessTokenOnly)
async def refresh_token(
    request: Request,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts the refresh token either from the httpOnly cookie (browser
    clients) or the request body (service-to-service / mobile clients).
    Rotates it and returns a fresh access token; the new refresh token is
    set as a cookie for browser clients.
    """
    presented = request.cookies.get(REFRESH_COOKIE_NAME) or (body.refresh_token if body else None)
    if not presented:
        raise InvalidTokenError("no refresh token provided")

    new_pair = await token_service.rotate_refresh_token(db, presented)

    response = JSONResponse(
        content=AccessTokenOnly(
            access_token=new_pair["access_token"],
            expires_in=new_pair["expires_in"],
        ).model_dump()
    )
    response.set_cookie(value=new_pair["refresh_token"], **_refresh_cookie_kwargs())
    return response


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if presented:
        try:
            payload = security.decode_token(presented, expected_type="refresh")
            result = await db.execute(select(RefreshToken).where(RefreshToken.jti == hash_jti(payload["jti"])))
            row = result.scalar_one_or_none()
            if row:
                await token_service.revoke_family(db, row.family_id)
        except Exception:
            pass  # logout is best-effort; an already-invalid/expired token is fine to ignore

    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return response


@router.get("/me", response_model=UserOut)
async def get_me(
    user_id: str = Depends(get_current_user_id_dep),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError("user not found", code="user_not_found", status_code=status.HTTP_404_NOT_FOUND)
    return user
