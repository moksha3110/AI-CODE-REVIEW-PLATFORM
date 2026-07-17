"""initial schema: installations, repositories, push_events, outbox_events

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
        "installations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("github_installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("connected_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_installations_github_installation_id", "installations", ["github_installation_id"], unique=True)
    op.create_index("ix_installations_connected_by_user_id", "installations", ["connected_by_user_id"])

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("installations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_repositories_github_repo_id", "repositories", ["github_repo_id"], unique=True)
    op.create_index("ix_repositories_installation_id", "repositories", ["installation_id"])

    op.create_table(
        "push_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_delivery_id", sa.String(64), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False),
        sa.Column("before_sha", sa.String(40), nullable=False),
        sa.Column("after_sha", sa.String(40), nullable=False),
        sa.Column("pusher_login", sa.String(255), nullable=False),
        sa.Column("commits", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_push_events_github_delivery_id", "push_events", ["github_delivery_id"], unique=True)
    op.create_index("ix_push_events_repository_id", "push_events", ["repository_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("routing_key", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("push_events")
    op.drop_table("repositories")
    op.drop_table("installations")
