"""
Persists one `review.completed` event as a Review + its FileReview rows,
in a single transaction. Idempotent on `push_event_id` - a redelivered or
duplicate message is a no-op, not a duplicate row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.file_review import FileReview
from app.models.review import Review

logger = get_logger(__name__)


class MalformedReviewPayloadError(ValueError):
    """The message body doesn't match the review.completed contract -
    retrying will never fix this, so callers should drop it rather than
    requeue."""


def _parse_payload(payload: dict) -> dict:
    try:
        return {
            "push_event_id": uuid.UUID(payload["push_event_id"]),
            "repository_id": uuid.UUID(payload["repository_id"]),
            "repository_full_name": str(payload["repository_full_name"]),
            "ref": str(payload["ref"]),
            "after_sha": str(payload["after_sha"]),
            "overall_complexity_score": float(payload["overall_complexity_score"]),
            "analyzed_at": datetime.fromisoformat(payload["analyzed_at"]),
            "file_reviews": payload["file_reviews"],
        }
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedReviewPayloadError(f"invalid review.completed payload: {exc}") from exc


async def ingest_review(db: AsyncSession, payload: dict) -> Review | None:
    fields = _parse_payload(payload)
    push_event_id = fields["push_event_id"]

    result = await db.execute(select(Review.id).where(Review.push_event_id == push_event_id))
    if result.scalar_one_or_none() is not None:
        logger.info("review_already_ingested", push_event_id=str(push_event_id))
        return None

    try:
        file_reviews_payload = fields["file_reviews"]
        total_bug_count = sum(len(fr["bugs"]) for fr in file_reviews_payload)
        total_security_issue_count = sum(len(fr["security_issues"]) for fr in file_reviews_payload)
    except (KeyError, TypeError) as exc:
        raise MalformedReviewPayloadError(f"invalid file_reviews entry: {exc}") from exc

    review = Review(
        id=uuid.uuid4(),
        push_event_id=push_event_id,
        repository_id=fields["repository_id"],
        repository_full_name=fields["repository_full_name"],
        ref=fields["ref"],
        after_sha=fields["after_sha"],
        overall_complexity_score=fields["overall_complexity_score"],
        total_bug_count=total_bug_count,
        total_security_issue_count=total_security_issue_count,
        analyzed_at=fields["analyzed_at"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(review)

    try:
        for file_review_payload in file_reviews_payload:
            db.add(
                FileReview(
                    id=uuid.uuid4(),
                    review_id=review.id,
                    file_path=str(file_review_payload["file_path"]),
                    summary=str(file_review_payload["summary"]),
                    complexity_score=float(file_review_payload["complexity_score"]),
                    bug_count=len(file_review_payload["bugs"]),
                    security_issue_count=len(file_review_payload["security_issues"]),
                    optimization_count=len(file_review_payload["optimizations"]),
                    bugs=file_review_payload["bugs"],
                    security_issues=file_review_payload["security_issues"],
                    optimizations=file_review_payload["optimizations"],
                    documentation_suggestions=file_review_payload["documentation_suggestions"],
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedReviewPayloadError(f"invalid file_reviews entry: {exc}") from exc

    try:
        await db.commit()
    except IntegrityError:
        # Two redeliveries raced past the SELECT above - the DB unique
        # constraint caught it instead. Converge onto whichever row won.
        await db.rollback()
        logger.info("review_ingest_race_lost", push_event_id=str(push_event_id))
        return None

    logger.info("review_ingested", push_event_id=str(push_event_id), files=len(file_reviews_payload))
    return review
