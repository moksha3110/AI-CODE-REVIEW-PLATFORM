"""initial schema: notifications

Revision ID: 0001
Revises:
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("push_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_full_name", sa.String(512), nullable=False),
        sa.Column("after_sha", sa.String(40), nullable=False),
        sa.Column("overall_complexity_score", sa.Float(), nullable=False),
        sa.Column("total_bug_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_security_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_push_event_id", "notifications", ["push_event_id"], unique=True)
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
