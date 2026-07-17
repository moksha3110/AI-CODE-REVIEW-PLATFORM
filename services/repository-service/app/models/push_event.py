import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# JSONB on Postgres (matches the migration); plain JSON elsewhere so the
# sqlite-backed test suite can still create these tables.
_JSONType = JSON().with_variant(JSONB(), "postgresql")


class PushEvent(Base):
    """
    One row per GitHub push webhook we've processed. `github_delivery_id`
    carries a unique constraint - that's the durable half of our idempotency
    story (Redis is the fast-path check; this is the backstop that survives
    a Redis flush or a race between concurrent pod replicas).
    """

    __tablename__ = "push_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_delivery_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    before_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    after_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    pusher_login: Mapped[str] = mapped_column(String(255), nullable=False)
    commits: Mapped[list] = mapped_column(_JSONType, nullable=False)  # [{sha, message, added, removed, modified}, ...]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
