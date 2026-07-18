from __future__ import annotations

import secrets
import uuid as uuid_module
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id_dep, get_redis
from app.core import github_app
from app.core.config import get_settings
from app.core.exceptions import InstallationNotFoundError
from app.db.session import get_db
from app.models.installation import Installation
from app.models.repository import Repository
from app.schemas.repository import InstallUrlOut, RepositoryOut
from app.services.installation_service import record_installation

router = APIRouter(prefix="/repositories", tags=["repositories"])

INSTALL_STATE_TTL_SECONDS = 600


@router.get("/install", response_model=InstallUrlOut)
async def start_installation(
    user_id: str = Depends(get_current_user_id_dep),
    redis: Redis = Depends(get_redis),
):
    """
    Returns the GitHub App installation URL for the frontend to redirect
    the browser to. We can't redirect directly from here the way Auth
    Service does with OAuth login, because this endpoint is called via an
    authenticated fetch (not a top-level navigation), so there's no
    Authorization header once GitHub redirects back - the `state` param is
    how we re-associate that later callback with this logged-in user.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    await redis.setex(f"install_state:{state}", INSTALL_STATE_TTL_SECONDS, user_id)

    params = {"state": state}
    url = f"https://github.com/apps/{settings.github_app_slug}/installations/new?{urlencode(params)}"
    return InstallUrlOut(install_url=url)


@router.get("/installations/callback")
async def installation_callback(
    installation_id: int,
    state: str,
    setup_action: str = "install",
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """GitHub redirects here after the user approves the installation."""
    state_key = f"install_state:{state}"
    user_id = await redis.get(state_key)
    if not user_id:
        raise InstallationNotFoundError("installation state missing, expired, or already used")
    await redis.delete(state_key)

    install_info = await github_app.fetch_installation_info(installation_id)

    await record_installation(
        db,
        redis,
        github_installation_id=installation_id,
        account_login=install_info["account"]["login"],
        account_type=install_info["account"]["type"],
        connected_by_user_id=uuid_module.UUID(user_id),
    )

    frontend_url = get_settings().frontend_url
    return RedirectResponse(url=f"{frontend_url}/repositories/connected?setup_action={setup_action}")


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(
    user_id: str = Depends(get_current_user_id_dep),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository)
        .join(Installation, Installation.id == Repository.installation_id)
        .where(Installation.connected_by_user_id == uuid_module.UUID(user_id))
        .order_by(Repository.full_name)
    )
    return result.scalars().all()
