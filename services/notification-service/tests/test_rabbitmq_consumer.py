import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services import rabbitmq_consumer
from app.services.notification_service import MalformedReviewPayloadError

pytestmark = pytest.mark.asyncio


def _fake_message(body: bytes) -> AsyncMock:
    message = AsyncMock()
    message.body = body
    return message


async def test_malformed_json_is_acked_not_nacked(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    message = _fake_message(b"not json")

    await rabbitmq_consumer._handle(message, session_factory)

    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_successful_processing_acks(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(rabbitmq_consumer, "notify_review_completed", AsyncMock(return_value=None))

    payload = f'{{"push_event_id": "{uuid.uuid4()}"}}'.encode()
    message = _fake_message(payload)

    await rabbitmq_consumer._handle(message, session_factory)

    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_malformed_payload_error_is_acked_not_nacked(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(
        rabbitmq_consumer,
        "notify_review_completed",
        AsyncMock(side_effect=MalformedReviewPayloadError("missing field")),
    )

    payload = f'{{"push_event_id": "{uuid.uuid4()}"}}'.encode()
    message = _fake_message(payload)

    await rabbitmq_consumer._handle(message, session_factory)

    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_transient_failure_requeues(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(
        rabbitmq_consumer, "notify_review_completed", AsyncMock(side_effect=RuntimeError("owner lookup failed"))
    )

    payload = f'{{"push_event_id": "{uuid.uuid4()}"}}'.encode()
    message = _fake_message(payload)

    await rabbitmq_consumer._handle(message, session_factory)

    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_called()
