import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """
    One row per push that made it all the way through the review pipeline,
    for the repository's owning user. `push_event_id` carries a unique
    constraint - the durable half of this service's idempotency story (a
    redelivered or duplicate "review.completed" message must not create a
    second notification).

    Denormalized fields (repository_full_name, the counts) exist so the
    notifications list can render without a join back to Review Service -
    this service never queries another service's database directly, only
    what arrived on the event it consumed.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    push_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    repository_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    after_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    overall_complexity_score: Mapped[float] = mapped_column(Float, nullable=False)
    total_bug_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_security_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
