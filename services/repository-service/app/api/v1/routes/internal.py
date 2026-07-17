from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api.deps import get_redis, require_internal_service
from app.core import github_app

router = APIRouter(prefix="/internal", tags=["internal"])


class InstallationTokenOut(BaseModel):
    token: str


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
