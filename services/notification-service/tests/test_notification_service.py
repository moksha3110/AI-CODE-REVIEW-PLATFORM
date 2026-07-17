import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.notification import Notification
from app.services import notification_service, repository_owner_client
from app.services.notification_service import MalformedReviewPayloadError, notify_review_completed

pytestmark = pytest.mark.asyncio

OWNER_ID = "22222222-2222-2222-2222-222222222222"


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
                "security_issues": [{"description": "sql injection", "severity": "high", "line": 5}],
                "optimizations": [],
                "documentation_suggestions": [],
            }
        ],
        "analyzed_at": "2026-07-18T12:00:00+00:00",
    }
    base.update(overrides)
    return base


async def test_notify_review_completed_creates_notification(db_session, monkeypatch):
    monkeypatch.setattr(repository_owner_client, "get_repository_owner", AsyncMock(return_value=OWNER_ID))

    payload = _payload()
    notification = await notify_review_completed(db_session, payload)

    assert notification is not None
    assert str(notification.user_id) == OWNER_ID
    assert notification.total_bug_count == 1
    assert notification.total_security_issue_count == 1
    assert "octo/hello-world" in notification.message
    assert notification.read_at is None


async def test_duplicate_push_event_notifies_once(db_session, monkeypatch):
    owner_mock = AsyncMock(return_value=OWNER_ID)
    monkeypatch.setattr(repository_owner_client, "get_repository_owner", owner_mock)

    payload = _payload()
    first = await notify_review_completed(db_session, payload)
    second = await notify_review_completed(db_session, payload)

    assert first is not None
    assert second is None
    assert owner_mock.await_count == 1  # second call skipped the owner lookup entirely

    result = await db_session.execute(
        select(Notification).where(Notification.push_event_id == uuid.UUID(payload["push_event_id"]))
    )
    assert len(result.scalars().all()) == 1


async def test_malformed_payload_raises_and_skips_owner_lookup(db_session, monkeypatch):
    owner_mock = AsyncMock(return_value=OWNER_ID)
    monkeypatch.setattr(repository_owner_client, "get_repository_owner", owner_mock)

    payload = _payload()
    del payload["repository_full_name"]

    with pytest.raises(MalformedReviewPayloadError):
        await notify_review_completed(db_session, payload)

    owner_mock.assert_not_called()
    result = await db_session.execute(select(Notification))
    assert result.scalars().all() == []


async def test_owner_lookup_failure_propagates_and_persists_nothing(db_session, monkeypatch):
    from app.core.exceptions import OwnerLookupError

    monkeypatch.setattr(
        notification_service.repository_owner_client,
        "get_repository_owner",
        AsyncMock(side_effect=OwnerLookupError("repository-service unreachable")),
    )

    payload = _payload()
    with pytest.raises(OwnerLookupError):
        await notify_review_completed(db_session, payload)

    result = await db_session.execute(select(Notification))
    assert result.scalars().all() == []
