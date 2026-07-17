import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.file_review import FileReview
from app.models.review import Review

pytestmark = pytest.mark.asyncio


async def _seed_review(
    db_session,
    repository_id: uuid.UUID,
    analyzed_at: datetime,
    complexity: float = 3.0,
) -> Review:
    review = Review(
        id=uuid.uuid4(),
        push_event_id=uuid.uuid4(),
        repository_id=repository_id,
        repository_full_name="octo/hello-world",
        ref="refs/heads/main",
        after_sha="a" * 40,
        overall_complexity_score=complexity,
        total_bug_count=1,
        total_security_issue_count=0,
        analyzed_at=analyzed_at,
        created_at=analyzed_at,
    )
    db_session.add(review)
    db_session.add(
        FileReview(
            id=uuid.uuid4(),
            review_id=review.id,
            file_path="main.py",
            summary="Looks fine.",
            complexity_score=complexity,
            bug_count=1,
            security_issue_count=0,
            optimization_count=0,
            bugs=[{"description": "bug", "severity": "low", "line": 1}],
            security_issues=[],
            optimizations=[],
            documentation_suggestions=[],
        )
    )
    await db_session.commit()
    return review


async def test_list_reviews_requires_auth(client):
    resp = await client.get(f"/api/v1/repositories/{uuid.uuid4()}/reviews")
    assert resp.status_code == 401


async def test_list_reviews_returns_paginated_newest_first(client, db_session, auth_headers):
    repository_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    older = await _seed_review(db_session, repository_id, now - timedelta(days=1))
    newer = await _seed_review(db_session, repository_id, now)

    resp = await client.get(f"/api/v1/repositories/{repository_id}/reviews", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(newer.id), str(older.id)]


async def test_get_review_detail_includes_file_reviews(client, db_session, auth_headers):
    review = await _seed_review(db_session, uuid.uuid4(), datetime.now(timezone.utc))

    resp = await client.get(f"/api/v1/reviews/{review.id}", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(review.id)
    assert len(body["file_reviews"]) == 1
    assert body["file_reviews"][0]["file_path"] == "main.py"


async def test_get_review_404_for_unknown_id(client, auth_headers):
    resp = await client.get(f"/api/v1/reviews/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "review_not_found"


async def test_quality_trends_ordered_oldest_first(client, db_session, auth_headers):
    repository_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    older = await _seed_review(db_session, repository_id, now - timedelta(days=1), complexity=2.0)
    newer = await _seed_review(db_session, repository_id, now, complexity=5.0)

    resp = await client.get(f"/api/v1/repositories/{repository_id}/quality-trends", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [point["overall_complexity_score"] for point in body] == [2.0, 5.0]
    assert older.analyzed_at < newer.analyzed_at
