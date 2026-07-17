import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.analysis_run import AnalysisRun
from app.services import rabbitmq_consumer

pytestmark = pytest.mark.asyncio


def _fake_message(body: bytes) -> AsyncMock:
    message = AsyncMock()
    message.body = body
    return message


async def test_malformed_message_is_acked_not_nacked(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    message = _fake_message(b"not json")

    await rabbitmq_consumer._handle(message, session_factory)

    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_successful_processing_acks(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(rabbitmq_consumer, "process_analysis_request", AsyncMock(return_value=None))

    payload = b'{"push_event_id": "' + str(uuid.uuid4()).encode() + b'"}'
    message = _fake_message(payload)

    await rabbitmq_consumer._handle(message, session_factory)

    message.ack.assert_awaited_once()
    message.nack.assert_not_called()


async def test_failure_under_retry_budget_requeues(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    push_event_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            AnalysisRun(
                id=uuid.uuid4(),
                push_event_id=push_event_id,
                repository_id=uuid.uuid4(),
                status="failed",
                attempts=1,  # below default MAX_ANALYSIS_ATTEMPTS=3
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    monkeypatch.setattr(rabbitmq_consumer, "process_analysis_request", AsyncMock(side_effect=RuntimeError("boom")))

    message = _fake_message(f'{{"push_event_id": "{push_event_id}"}}'.encode())
    await rabbitmq_consumer._handle(message, session_factory)

    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_called()


async def test_failure_at_retry_budget_drops_message(db_engine, monkeypatch):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    push_event_id = uuid.uuid4()

    async with session_factory() as session:
        session.add(
            AnalysisRun(
                id=uuid.uuid4(),
                push_event_id=push_event_id,
                repository_id=uuid.uuid4(),
                status="failed",
                attempts=3,  # at default MAX_ANALYSIS_ATTEMPTS
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    monkeypatch.setattr(rabbitmq_consumer, "process_analysis_request", AsyncMock(side_effect=RuntimeError("boom")))

    message = _fake_message(f'{{"push_event_id": "{push_event_id}"}}'.encode())
    await rabbitmq_consumer._handle(message, session_factory)

    message.nack.assert_awaited_once_with(requeue=False)
    message.ack.assert_not_called()
