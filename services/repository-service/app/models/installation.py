import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Installation(Base):
    """One row per GitHub App installation (one GitHub user/org installing
    the app, possibly across many repos)."""

    __tablename__ = "installations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "User" | "Organization"
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
