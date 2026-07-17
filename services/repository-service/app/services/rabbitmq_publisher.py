"""
Thin wrapper around aio-pika for publishing to the platform's shared topic
exchange. Deliberately minimal: connection/channel are opened once and
reused (RabbitMQ connections are expensive to open per-message), and every
publish is persistent (survives a broker restart) since these are business
events, not disposable notifications.
"""
from __future__ import annotations

import json

import aio_pika
from aio_pika import ExchangeType, Message

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RabbitMQPublisher:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.Channel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        settings = get_settings()
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        self._exchange = await self._channel.declare_exchange(
            settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True
        )
        logger.info("rabbitmq_connected", exchange=settings.rabbitmq_exchange)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    async def publish(self, routing_key: str, payload: dict) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQPublisher.connect() must be called before publish()")

        message = Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)


_publisher: RabbitMQPublisher | None = None


async def get_publisher() -> RabbitMQPublisher:
    global _publisher
    if _publisher is None:
        _publisher = RabbitMQPublisher()
        await _publisher.connect()
    return _publisher
