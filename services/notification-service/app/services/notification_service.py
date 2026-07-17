"""
Turns one `review.completed` event into a Notification for the repository's
owning user. Idempotent on `push_event_id` - a redelivered or duplicate
message is a no-op, not a duplicate notification.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.notification import Notification
from app.services import repository_owner_client

logger = get_logger(__name__)


class MalformedReviewPayloadError(ValueError):
    """The message body doesn't match the review.completed contract -
    retrying will never fix this, so callers should drop it rather than
    requeue."""


def _parse_payload(payload: dict) -> dict:
    try:
        file_reviews = payload["file_reviews"]
        return {
            "push_event_id": uuid.UUID(payload["push_event_id"]),
            "repository_id": uuid.UUID(payload["repository_id"]),
            "repository_full_name": str(payload["repository_full_name"]),
            "after_sha": str(payload["after_sha"]),
            "overall_complexity_score": float(payload["overall_complexity_score"]),
            "total_bug_count": sum(len(fr["bugs"]) for fr in file_reviews),
            "total_security_issue_count": sum(len(fr["security_issues"]) for fr in file_reviews),
        }
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedReviewPayloadError(f"invalid review.completed payload: {exc}") from exc


def _build_message(fields: dict) -> str:
    return (
        f"Review complete for {fields['repository_full_name']}@{fields['after_sha'][:7]}: "
        f"{fields['total_bug_count']} bug(s), {fields['total_security_issue_count']} security "
        f"issue(s) found (complexity {fields['overall_complexity_score']:.1f}/10)."
    )


async def notify_review_completed(db: AsyncSession, payload: dict) -> Notification | None:
    fields = _parse_payload(payload)
    push_event_id = fields["push_event_id"]

    result = await db.execute(select(Notification.id).where(Notification.push_event_id == push_event_id))
    if result.scalar_one_or_none() is not None:
        logger.info("notification_already_sent", push_event_id=str(push_event_id))
        return None

    user_id = await repository_owner_client.get_repository_owner(str(fields["repository_id"]))

    notification = Notification(
        id=uuid.uuid4(),
        push_event_id=push_event_id,
        user_id=uuid.UUID(user_id),
        repository_id=fields["repository_id"],
        repository_full_name=fields["repository_full_name"],
        after_sha=fields["after_sha"],
        overall_complexity_score=fields["overall_complexity_score"],
        total_bug_count=fields["total_bug_count"],
        total_security_issue_count=fields["total_security_issue_count"],
        message=_build_message(fields),
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)

    try:
        await db.commit()
    except IntegrityError:
        # Two redeliveries raced past the SELECT above - the DB unique
        # constraint caught it instead. Converge onto whichever row won.
        await db.rollback()
        logger.info("notification_ingest_race_lost", push_event_id=str(push_event_id))
        return None

    logger.info("notification_created", push_event_id=str(push_event_id), user_id=user_id)
    return notification
