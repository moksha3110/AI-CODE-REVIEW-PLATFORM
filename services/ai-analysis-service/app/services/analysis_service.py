"""
Orchestrates one push event's worth of AI code review: claim (idempotency +
retry ledger) -> mint a clone token -> fetch changed files -> review each
with Claude -> persist the completed run and publish `review.completed` via
the transactional outbox, all in one commit.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.analysis_run import AnalysisRun
from app.models.outbox_event import OutboxEvent
from app.services import ai_client, git_service, installation_token_client

logger = get_logger(__name__)


async def _claim_run(db: AsyncSession, push_event_id: uuid.UUID, repository_id: uuid.UUID) -> AnalysisRun | None:
    """
    Returns the AnalysisRun to process, or None if this push_event should be
    skipped (already completed, or has exhausted its retry budget).
    Idempotent under concurrent/duplicate delivery: two workers racing to
    claim the same push_event_id converge onto the same row via the unique
    constraint - same pattern as Repository Service's installation upsert.
    """
    settings = get_settings()
    result = await db.execute(select(AnalysisRun).where(AnalysisRun.push_event_id == push_event_id))
    run = result.scalar_one_or_none()

    if run is None:
        run = AnalysisRun(
            id=uuid.uuid4(),
            push_event_id=push_event_id,
            repository_id=repository_id,
            status="processing",
            attempts=1,
            created_at=datetime.now(timezone.utc),
        )
        db.add(run)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            result = await db.execute(select(AnalysisRun).where(AnalysisRun.push_event_id == push_event_id))
            run = result.scalar_one()
        else:
            await db.commit()
            return run

    if run.status == "completed":
        return None
    if run.attempts >= settings.max_analysis_attempts:
        logger.warning(
            "analysis_run_retry_budget_exhausted", push_event_id=str(push_event_id), attempts=run.attempts
        )
        return None

    run.status = "processing"
    run.attempts += 1
    await db.commit()
    return run


async def process_analysis_request(db: AsyncSession, payload: dict) -> None:
    push_event_id = uuid.UUID(payload["push_event_id"])
    repository_id = uuid.UUID(payload["repository_id"])

    run = await _claim_run(db, push_event_id, repository_id)
    if run is None:
        logger.info("analysis_run_skipped", push_event_id=str(push_event_id))
        return

    try:
        token = await installation_token_client.get_installation_token(payload["github_installation_id"])
        files = await git_service.fetch_changed_files(
            repo_full_name=payload["repository_full_name"],
            after_sha=payload["after_sha"],
            changed_files=payload["changed_files"],
            token=token,
        )

        file_reviews = []
        for file_path, content in files.items():
            review = await ai_client.review_file(file_path, content)
            file_reviews.append(asdict(review))

        overall_complexity = (
            sum(r["complexity_score"] for r in file_reviews) / len(file_reviews) if file_reviews else 0.0
        )

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = None

        outbox_row = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type="analysis_run",
            aggregate_id=run.id,
            routing_key="review.completed",
            payload={
                "analysis_run_id": str(run.id),
                "push_event_id": str(push_event_id),
                "repository_id": str(repository_id),
                "repository_full_name": payload["repository_full_name"],
                "ref": payload["ref"],
                "after_sha": payload["after_sha"],
                "overall_complexity_score": round(overall_complexity, 2),
                "file_reviews": file_reviews,
                "analyzed_at": run.completed_at.isoformat(),
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(outbox_row)
        await db.commit()

        logger.info(
            "analysis_run_completed",
            push_event_id=str(push_event_id),
            files_reviewed=len(file_reviews),
        )
    except Exception as exc:
        await db.rollback()
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        await db.commit()
        logger.error("analysis_run_failed", push_event_id=str(push_event_id), error=str(exc))
        raise
