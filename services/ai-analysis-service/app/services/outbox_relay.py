"""
Polls `outbox_events` for unpublished rows and hands them to RabbitMQ.

Runs as a background asyncio task inside the same process for this portfolio
project's scale (same documented trade-off as Repository Service). At real
production scale this would be its own tiny deployable so it can be scaled
and restarted independently of the consumer process.

`SELECT ... FOR UPDATE SKIP LOCKED` is what makes it safe to run more than
one replica of this relay concurrently: each replica locks a different
batch of rows instead of racing on the same ones.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.outbox_event import OutboxEvent
from app.services.rabbitmq_publisher import RabbitMQPublisher

logger = get_logger(__name__)


async def relay_once(session_factory: async_sessionmaker, publisher: RabbitMQPublisher) -> int:
    """Publishes one batch of pending outbox events. Returns how many were sent."""
    settings = get_settings()
    published = 0

    async with session_factory() as session:
        result = await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(settings.outbox_relay_batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = result.scalars().all()

        for row in rows:
            try:
                await publisher.publish(row.routing_key, row.payload)
                row.published_at = datetime.now(timezone.utc)
                published += 1
            except Exception:
                row.attempts += 1
                logger.warning(
                    "outbox_publish_failed",
                    outbox_id=str(row.id),
                    routing_key=row.routing_key,
                    attempts=row.attempts,
                )
                # Left unpublished - retried on the next tick. A row that keeps
                # failing past a sane attempt count belongs in a dead-letter
                # table for manual inspection; same documented gap as Repository Service.

        await session.commit()

    return published


async def run_outbox_relay(session_factory: async_sessionmaker, publisher: RabbitMQPublisher) -> None:
    settings = get_settings()
    logger.info("outbox_relay_started", interval=settings.outbox_relay_interval_seconds)
    while True:
        try:
            count = await relay_once(session_factory, publisher)
            if count:
                logger.info("outbox_relay_batch_published", count=count)
        except Exception:
            logger.exception("outbox_relay_tick_failed")
        await asyncio.sleep(settings.outbox_relay_interval_seconds)
