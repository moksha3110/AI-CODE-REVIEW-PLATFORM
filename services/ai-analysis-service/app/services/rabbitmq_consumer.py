"""
Consumes `analysis.requested` events from the shared topic exchange and runs
each one through the AI review pipeline. Runs as a background asyncio task
in this same process (same documented trade-off as the outbox relay - see
README) rather than as a separately-scaled worker deployment.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.analysis_run import AnalysisRun
from app.services.analysis_service import process_analysis_request

logger = get_logger(__name__)


async def _handle(message: AbstractIncomingMessage, session_factory: async_sessionmaker) -> None:
    settings = get_settings()

    try:
        payload = json.loads(message.body)
        push_event_id = payload["push_event_id"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("analysis_request_malformed", error=str(exc))
        await message.ack()  # poison message - retrying won't fix a parse error
        return

    logger.info("analysis_request_received", push_event_id=push_event_id)

    async with session_factory() as session:
        try:
            await process_analysis_request(session, payload)
        except Exception:
            # process_analysis_request already logged the failure and
            # recorded it against the run's retry ledger (attempts vs
            # max_analysis_attempts). Requeue so RabbitMQ redelivers and a
            # future claim can retry, unless the ledger says the retry
            # budget is exhausted - then drop it (ack) rather than loop
            # forever. A message stuck at the retry cap becomes a job for
            # manual/alerted follow-up - a documented gap, same as the
            # outbox relay's missing dead-letter table.
            result = await session.execute(
                select(AnalysisRun.attempts).where(AnalysisRun.push_event_id == uuid.UUID(push_event_id))
            )
            attempts = result.scalar_one_or_none() or settings.max_analysis_attempts
            await message.nack(requeue=attempts < settings.max_analysis_attempts)
            return

    await message.ack()


async def run_consumer(session_factory: async_sessionmaker) -> None:
    settings = get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)

        exchange = await channel.declare_exchange(settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(settings.rabbitmq_consume_queue, durable=True)
        await queue.bind(exchange, routing_key=settings.rabbitmq_consume_routing_key)

        logger.info(
            "consumer_started",
            queue=settings.rabbitmq_consume_queue,
            routing_key=settings.rabbitmq_consume_routing_key,
        )

        async def _on_message(message: AbstractIncomingMessage) -> None:
            await _handle(message, session_factory)

        await queue.consume(_on_message)

        # Block for the lifetime of the task - cancelled by the app's lifespan on shutdown.
        await asyncio.Future()
