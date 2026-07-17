import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.file_review import FileReview


class Review(Base):
    """
    One row per push event that made it through the AI analysis pipeline.
    `push_event_id` carries a unique constraint - the durable half of this
    service's idempotency story (a redelivered or duplicate
    "review.completed" message must not create a second review).
    """

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    push_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    repository_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    after_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    overall_complexity_score: Mapped[float] = mapped_column(Float, nullable=False)
    total_bug_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_security_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    file_reviews: Mapped[list["FileReview"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="FileReview.file_path"
    )
