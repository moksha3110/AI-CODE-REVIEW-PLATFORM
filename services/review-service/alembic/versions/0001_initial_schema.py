"""initial schema: reviews, file_reviews

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
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("push_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_full_name", sa.String(512), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False),
        sa.Column("after_sha", sa.String(40), nullable=False),
        sa.Column("overall_complexity_score", sa.Float(), nullable=False),
        sa.Column("total_bug_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_security_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_push_event_id", "reviews", ["push_event_id"], unique=True)
    op.create_index("ix_reviews_repository_id", "reviews", ["repository_id"])
    op.create_index("ix_reviews_repository_id_analyzed_at", "reviews", ["repository_id", "analyzed_at"])

    op.create_table(
        "file_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("summary", sa.String(2000), nullable=False),
        sa.Column("complexity_score", sa.Float(), nullable=False),
        sa.Column("bug_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("security_issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("optimization_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bugs", postgresql.JSONB(), nullable=False),
        sa.Column("security_issues", postgresql.JSONB(), nullable=False),
        sa.Column("optimizations", postgresql.JSONB(), nullable=False),
        sa.Column("documentation_suggestions", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_file_reviews_review_id", "file_reviews", ["review_id"])


def downgrade() -> None:
    op.drop_table("file_reviews")
    op.drop_table("reviews")
