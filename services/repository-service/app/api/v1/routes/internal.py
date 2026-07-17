from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, require_internal_service
from app.core import github_app
from app.core.exceptions import RepositoryNotFoundError
from app.db.session import get_db
from app.models.installation import Installation
from app.models.repository import Repository

router = APIRouter(prefix="/internal", tags=["internal"])


class InstallationTokenOut(BaseModel):
    token: str


class RepositoryOwnerOut(BaseModel):
    user_id: str


@router.get(
    "/installations/{installation_id}/token",
    response_model=InstallationTokenOut,
    dependencies=[Depends(require_internal_service)],
)
async def get_installation_token_for_service(
    installation_id: int,
    redis: Redis = Depends(get_redis),
):
    """
    The GitHub App private key never leaves this service. AI Analysis
    Service (or anything else that needs to clone a repo) calls this
    endpoint instead of minting tokens itself - keeping exactly one
    service responsible for that credential, and one place to audit or
    revoke access from.
    """
    token = await github_app.get_installation_token(redis, installation_id)
    return InstallationTokenOut(token=token)


@router.get(
    "/repositories/{repository_id}/owner",
    response_model=RepositoryOwnerOut,
    dependencies=[Depends(require_internal_service)],
)
async def get_repository_owner(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Repository Service is the only service that knows which platform user
    connected a given repo (via the Installation it belongs to) - other
    services that need "who owns this repo" (e.g. Notification Service,
    deciding who to notify) call this instead of duplicating that mapping.
    """
    result = await db.execute(
        select(Installation.connected_by_user_id)
        .join(Repository, Repository.installation_id == Installation.id)
        .where(Repository.id == repository_id)
    )
    user_id = result.scalar_one_or_none()
    if user_id is None:
        raise RepositoryNotFoundError(f"no repository with id={repository_id}")
    return RepositoryOwnerOut(user_id=str(user_id))
