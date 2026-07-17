from __future__ import annotations

import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.core.logging import get_logger
from app.models.installation import Installation
from app.models.outbox_event import OutboxEvent
from app.models.push_event import PushEvent
from app.models.repository import Repository

logger = get_logger(__name__)


async def _already_processed(redis: Redis, delivery_id: str) -> bool:
    """Fast-path idempotency check. The DB unique constraint on
    github_delivery_id is the real backstop; this just avoids a wasted
    DB round-trip for the common case of GitHub retrying a delivery we
    already handled seconds ago."""
    settings = get_settings()
    key = f"webhook_delivery:{delivery_id}"
    was_set = await redis.set(key, "1", nx=True, ex=settings.webhook_dedup_ttl_seconds)
    return not was_set  # SET NX returns None if the key already existed


async def process_push_event(
    db: AsyncSession,
    redis: Redis,
    delivery_id: str,
    payload: dict,
) -> uuid.UUID | None:
    """
    Returns the new PushEvent's id, or None if this delivery was already
    processed (duplicate - not an error, just a no-op).
    """
    if await _already_processed(redis, delivery_id):
        logger.info("webhook_duplicate_skipped", delivery_id=delivery_id)
        return None

    github_repo_id = payload["repository"]["id"]
    result = await db.execute(select(Repository).where(Repository.github_repo_id == github_repo_id))
    repository = result.scalar_one_or_none()
    if repository is None:
        # We received a webhook for a repo we don't have a record of - most
        # likely the install-time repo sync hasn't caught up yet, or the
        # installation was modified to add this repo after the fact.
        raise RepositoryNotFoundError(
            f"no repository record for github_repo_id={github_repo_id}; is it fully installed?"
        )

    installation_result = await db.execute(
        select(Installation.github_installation_id).where(Installation.id == repository.installation_id)
    )
    github_installation_id = installation_result.scalar_one()

    commits = [
        {
            "sha": c["id"],
            "message": c["message"],
            "author": c["author"]["name"],
            "added": c.get("added", []),
            "removed": c.get("removed", []),
            "modified": c.get("modified", []),
        }
        for c in payload.get("commits", [])
    ]

    push_event = PushEvent(
        id=uuid.uuid4(),
        repository_id=repository.id,
        github_delivery_id=delivery_id,
        ref=payload["ref"],
        before_sha=payload["before"],
        after_sha=payload["after"],
        pusher_login=payload.get("pusher", {}).get("name", "unknown"),
        commits=commits,
        received_at=datetime.now(timezone.utc),
    )

    outbox_row = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_type="push_event",
        aggregate_id=push_event.id,
        routing_key="analysis.requested",
        payload={
            "push_event_id": str(push_event.id),
            "repository_id": str(repository.id),
            "repository_full_name": repository.full_name,
            "installation_id": str(repository.installation_id),
            "github_installation_id": github_installation_id,
            "ref": push_event.ref,
            "before_sha": push_event.before_sha,
            "after_sha": push_event.after_sha,
            "changed_files": sorted(
                {f for c in commits for f in (c["added"] + c["modified"])}
            ),
        },
        created_at=datetime.now(timezone.utc),
    )

    try:
        db.add(push_event)
        db.add(outbox_row)
        # Same transaction, same commit - this IS the outbox pattern.
        await db.commit()
    except IntegrityError:
        # Two concurrent deliveries with the same ID raced past the Redis
        # check (small window) - the DB unique constraint caught it instead.
        await db.rollback()
        logger.info("webhook_duplicate_caught_by_db_constraint", delivery_id=delivery_id)
        return None

    logger.info(
        "push_event_processed",
        repository=repository.full_name,
        after_sha=push_event.after_sha,
        commit_count=len(commits),
    )
    return push_event.id
