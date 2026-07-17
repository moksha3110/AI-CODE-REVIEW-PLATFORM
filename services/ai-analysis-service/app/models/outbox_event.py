import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# JSONB on Postgres; plain JSON elsewhere so the sqlite-backed test suite can
# still create these tables.
_JSONType = JSON().with_variant(JSONB(), "postgresql")


class OutboxEvent(Base):
    """
    Same transactional-outbox pattern as Repository Service: the completed
    (or failed) review is written to `analysis_runs` AND a row here in the
    SAME database transaction, so "finish the analysis" and "publish
    review.completed" either both happen or neither does. A relay process
    reads unpublished rows and hands them to RabbitMQ.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "analysis_run"
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "review.completed"
    payload: Mapped[dict] = mapped_column(_JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
