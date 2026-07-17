import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# JSONB on Postgres (matches the migration); plain JSON elsewhere so the
# sqlite-backed test suite can still create these tables.
_JSONType = JSON().with_variant(JSONB(), "postgresql")


class OutboxEvent(Base):
    """
    The transactional outbox. Repository Service writes a business record
    (a PushEvent) AND a row here in the SAME database transaction - so
    either both happen or neither does. A separate relay process then reads
    unpublished rows and publishes them to RabbitMQ, marking them sent.

    This is what makes "clone push processing + publish an event" atomic
    without a distributed transaction: the write to Postgres is the only
    thing that has to succeed synchronously; publishing to the broker can
    be retried indefinitely afterward without losing or duplicating the
    original business fact.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "push_event"
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "analysis.requested"
    payload: Mapped[dict] = mapped_column(_JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
