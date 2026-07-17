import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.notification import Notification
from tests.conftest import TEST_USER_ID

pytestmark = pytest.mark.asyncio


async def _seed_notification(
    db_session,
    user_id: str = TEST_USER_ID,
    created_at: datetime | None = None,
    read: bool = False,
) -> Notification:
    created_at = created_at or datetime.now(timezone.utc)
    notification = Notification(
        id=uuid.uuid4(),
        push_event_id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        repository_id=uuid.uuid4(),
        repository_full_name="octo/hello-world",
        after_sha="a" * 40,
        overall_complexity_score=3.0,
        total_bug_count=1,
        total_security_issue_count=0,
        message="Review complete for octo/hello-world@aaaaaaa: 1 bug(s), 0 security issue(s) found.",
        read_at=created_at if read else None,
        created_at=created_at,
    )
    db_session.add(notification)
    await db_session.commit()
    return notification


async def test_list_notifications_requires_auth(client):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401


async def test_list_notifications_scoped_to_current_user(client, db_session, auth_headers):
    mine = await _seed_notification(db_session)
    await _seed_notification(db_session, user_id="99999999-9999-9999-9999-999999999999")

    resp = await client.get("/api/v1/notifications", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["unread_count"] == 1
    assert body["items"][0]["id"] == str(mine.id)


async def test_list_notifications_unread_only_filter(client, db_session, auth_headers):
    await _seed_notification(db_session, read=True)
    unread = await _seed_notification(db_session, created_at=datetime.now(timezone.utc) + timedelta(seconds=1))

    resp = await client.get("/api/v1/notifications", params={"unread_only": True}, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["unread_count"] == 1
    assert body["items"][0]["id"] == str(unread.id)


async def test_mark_notification_read(client, db_session, auth_headers):
    notification = await _seed_notification(db_session)

    resp = await client.post(f"/api/v1/notifications/{notification.id}/read", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None

    follow_up = await client.get("/api/v1/notifications", headers=auth_headers)
    assert follow_up.json()["unread_count"] == 0


async def test_mark_notification_read_404_for_other_users_notification(client, db_session, auth_headers):
    notification = await _seed_notification(db_session, user_id="99999999-9999-9999-9999-999999999999")

    resp = await client.post(f"/api/v1/notifications/{notification.id}/read", headers=auth_headers)

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "notification_not_found"
