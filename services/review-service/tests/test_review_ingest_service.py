import uuid

import pytest
from sqlalchemy import select

from app.models.file_review import FileReview
from app.models.review import Review
from app.services.review_ingest_service import MalformedReviewPayloadError, ingest_review

pytestmark = pytest.mark.asyncio


def _payload(**overrides) -> dict:
    base = {
        "analysis_run_id": str(uuid.uuid4()),
        "push_event_id": str(uuid.uuid4()),
        "repository_id": str(uuid.uuid4()),
        "repository_full_name": "octo/hello-world",
        "ref": "refs/heads/main",
        "after_sha": "a" * 40,
        "overall_complexity_score": 4.5,
        "file_reviews": [
            {
                "file_path": "main.py",
                "summary": "Adds a new endpoint.",
                "complexity_score": 4.5,
                "bugs": [{"description": "off by one", "severity": "medium", "line": 12}],
                "security_issues": [],
                "optimizations": [{"description": "cache this", "line": 30}],
                "documentation_suggestions": ["add a docstring"],
            }
        ],
        "analyzed_at": "2026-07-18T12:00:00+00:00",
    }
    base.update(overrides)
    return base


async def test_ingest_review_creates_review_and_file_reviews(db_session):
    payload = _payload()

    review = await ingest_review(db_session, payload)

    assert review is not None
    assert review.repository_full_name == "octo/hello-world"
    assert review.total_bug_count == 1
    assert review.total_security_issue_count == 0

    file_review_result = await db_session.execute(select(FileReview).where(FileReview.review_id == review.id))
    file_review = file_review_result.scalar_one()
    assert file_review.file_path == "main.py"
    assert file_review.bug_count == 1
    assert file_review.optimization_count == 1


async def test_duplicate_push_event_is_ingested_once(db_session):
    payload = _payload()

    first = await ingest_review(db_session, payload)
    second = await ingest_review(db_session, payload)

    assert first is not None
    assert second is None

    result = await db_session.execute(
        select(Review).where(Review.push_event_id == uuid.UUID(payload["push_event_id"]))
    )
    assert len(result.scalars().all()) == 1


async def test_malformed_payload_raises_and_persists_nothing(db_session):
    payload = _payload()
    del payload["repository_full_name"]

    with pytest.raises(MalformedReviewPayloadError):
        await ingest_review(db_session, payload)

    result = await db_session.execute(select(Review))
    assert result.scalars().all() == []
