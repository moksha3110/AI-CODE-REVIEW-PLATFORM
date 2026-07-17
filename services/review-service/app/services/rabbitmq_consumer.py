"""
Consumes `review.completed` events from the shared topic exchange and
persists each one. Runs as a background asyncio task inside this same
process - same documented trade-off as the other services' background
workers (see README).
"""
from __future__ import annotations

import asyncio
import json

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.review_ingest_service import MalformedReviewPayloadError, ingest_review

logger = get_logger(__name__)


async def _handle(message: AbstractIncomingMessage, session_factory: async_sessionmaker) -> None:
    try:
        payload = json.loads(message.body)
        push_event_id = payload["push_event_id"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("review_completed_malformed", error=str(exc))
        await message.ack()  # poison message - retrying won't fix a parse error
        return

    logger.info("review_completed_received", push_event_id=push_event_id)

    async with session_factory() as session:
        try:
            await ingest_review(session, payload)
        except MalformedReviewPayloadError as exc:
            logger.error("review_completed_malformed", push_event_id=push_event_id, error=str(exc))
            await message.ack()  # same story - a schema mismatch never resolves itself on retry
            return
        except Exception:
            logger.exception("review_ingest_failed", push_event_id=push_event_id)
            await message.nack(requeue=True)  # transient (DB hiccup, etc.) - let RabbitMQ redeliver
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
