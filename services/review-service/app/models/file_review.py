import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review

# JSONB on Postgres; plain JSON elsewhere so the sqlite-backed test suite can
# still create these tables.
_JSONType = JSON().with_variant(JSONB(), "postgresql")


class FileReview(Base):
    """
    One row per file the AI Analysis Service reviewed within a push.
    `bug_count`/`security_issue_count`/`optimization_count` are denormalized
    from the `bugs`/`security_issues`/`optimizations` JSON columns at ingest
    time - a deliberate trade-off so the quality-trends endpoint can
    aggregate with plain SQL instead of unpacking JSON per row on every
    request.
    """

    __tablename__ = "file_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    complexity_score: Mapped[float] = mapped_column(nullable=False)
    bug_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    security_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    optimization_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bugs: Mapped[list] = mapped_column(_JSONType, nullable=False)
    security_issues: Mapped[list] = mapped_column(_JSONType, nullable=False)
    optimizations: Mapped[list] = mapped_column(_JSONType, nullable=False)
    documentation_suggestions: Mapped[list] = mapped_column(_JSONType, nullable=False)

    review: Mapped["Review"] = relationship(back_populates="file_reviews")
