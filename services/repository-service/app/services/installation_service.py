from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import github_app
from app.core.logging import get_logger
from app.models.installation import Installation
from app.models.repository import Repository

logger = get_logger(__name__)


async def record_installation(
    db: AsyncSession,
    redis: Redis,
    github_installation_id: int,
    account_login: str,
    account_type: str,
    connected_by_user_id: uuid.UUID,
) -> Installation:
    """
    Upserts the Installation row, then pulls the current repo list from
    GitHub and upserts each one into `repositories`. Idempotent by design -
    GitHub can re-send installation events (e.g. permissions changed), and
    re-running this should just converge to the same state.
    """
    result = await db.execute(
        select(Installation).where(Installation.github_installation_id == github_installation_id)
    )
    installation = result.scalar_one_or_none()

    if installation is None:
        installation = Installation(
            id=uuid.uuid4(),
            github_installation_id=github_installation_id,
            account_login=account_login,
            account_type=account_type,
            connected_by_user_id=connected_by_user_id,
        )
        db.add(installation)
        try:
            await db.flush()  # need installation.id before we can attach repositories to it
        except IntegrityError:
            # Two concurrent installation callbacks raced past the SELECT
            # above - the DB unique constraint caught it instead. Converge
            # onto whichever row won.
            await db.rollback()
            result = await db.execute(
                select(Installation).where(
                    Installation.github_installation_id == github_installation_id
                )
            )
            installation = result.scalar_one()

    token = await github_app.get_installation_token(redis, github_installation_id)
    repos = await github_app.fetch_installation_repositories(token)

    for repo in repos:
        existing = await db.execute(select(Repository).where(Repository.github_repo_id == repo["id"]))
        row = existing.scalar_one_or_none()
        if row is None:
            db.add(
                Repository(
                    id=uuid.uuid4(),
                    installation_id=installation.id,
                    github_repo_id=repo["id"],
                    full_name=repo["full_name"],
                    default_branch=repo.get("default_branch", "main"),
                    is_private=repo.get("private", True),
                )
            )
        else:
            row.full_name = repo["full_name"]
            row.default_branch = repo.get("default_branch", row.default_branch)
            row.is_private = repo.get("private", row.is_private)

    await db.commit()
    logger.info("installation_synced", account=account_login, repo_count=len(repos))
    return installation
