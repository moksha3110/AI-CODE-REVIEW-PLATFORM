import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.installation import Installation
from app.models.outbox_event import OutboxEvent
from app.models.push_event import PushEvent
from app.models.repository import Repository
from app.services.outbox_relay import relay_once

pytestmark = pytest.mark.asyncio

WEBHOOK_SECRET = "test-webhook-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _push_payload(delivery_repo_id: int = 999, after_sha: str = "a" * 40) -> dict:
    return {
        "ref": "refs/heads/main",
        "before": "b" * 40,
        "after": after_sha,
        "repository": {"id": delivery_repo_id, "full_name": "octo/hello-world"},
        "pusher": {"name": "octocat"},
        "commits": [
            {
                "id": after_sha,
                "message": "fix: handle edge case",
                "author": {"name": "octocat"},
                "added": ["new_file.py"],
                "removed": [],
                "modified": ["main.py"],
            }
        ],
    }


async def _seed_repository(db_session, github_repo_id: int) -> Repository:
    installation = Installation(
        id=uuid.uuid4(),
        github_installation_id=12345,
        account_login="octo",
        account_type="Organization",
        connected_by_user_id=uuid.uuid4(),
    )
    repo = Repository(
        id=uuid.uuid4(),
        installation_id=installation.id,
        github_repo_id=github_repo_id,
        full_name="octo/hello-world",
        default_branch="main",
        is_private=True,
    )
    db_session.add(installation)
    db_session.add(repo)
    await db_session.commit()
    return repo


async def test_webhook_rejects_invalid_signature(client):
    body = json.dumps(_push_payload()).encode()
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_webhook_signature"


async def test_webhook_ping_event_acknowledged(client):
    body = json.dumps({"zen": "hello"}).encode()
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pong"


async def test_push_for_unknown_repository_returns_404(client):
    body = json.dumps(_push_payload(delivery_repo_id=404404)).encode()
    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "repository_not_found"


async def test_push_event_persisted_with_outbox_row(client, db_session, db_engine):
    repo = await _seed_repository(db_session, github_repo_id=555)

    payload = _push_payload(delivery_repo_id=555)
    body = json.dumps(payload).encode()
    delivery_id = str(uuid.uuid4())

    resp = await client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] is True

    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        push_result = await session.execute(select(PushEvent).where(PushEvent.github_delivery_id == delivery_id))
        push_event = push_result.scalar_one()
        assert push_event.repository_id == repo.id
        assert push_event.after_sha == payload["after"]

        outbox_result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == push_event.id)
        )
        outbox_row = outbox_result.scalar_one()
        assert outbox_row.routing_key == "analysis.requested"
        assert outbox_row.published_at is None
        assert outbox_row.payload["repository_full_name"] == "octo/hello-world"
        assert set(outbox_row.payload["changed_files"]) == {"new_file.py", "main.py"}


async def test_duplicate_delivery_id_is_idempotent(client, db_session):
    await _seed_repository(db_session, github_repo_id=777)

    payload = _push_payload(delivery_repo_id=777)
    body = json.dumps(payload).encode()
    delivery_id = str(uuid.uuid4())
    headers = {
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": _sign(body),
    }

    first = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
    second = await client.post("/api/v1/webhooks/github", content=body, headers=headers)

    assert first.status_code == 200 and first.json()["processed"] is True
    assert second.status_code == 200 and second.json()["processed"] is False


async def test_outbox_relay_publishes_and_marks_rows_sent(db_engine, mock_publisher):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await _seed_repository(session, github_repo_id=888)

    from datetime import datetime, timezone

    async with session_factory() as session:
        row = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type="push_event",
            aggregate_id=uuid.uuid4(),
            routing_key="analysis.requested",
            payload={"hello": "world"},
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()

    published_count = await relay_once(session_factory, mock_publisher)

    assert published_count == 1
    mock_publisher.publish.assert_awaited_once_with("analysis.requested", {"hello": "world"})

    async with session_factory() as session:
        result = await session.execute(select(OutboxEvent))
        refreshed = result.scalar_one()
        assert refreshed.published_at is not None
