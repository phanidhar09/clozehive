"""Add chat session summary + daily FANI nudges.

Revision ID: 025
Revises: 024
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ai_chat_sessions: rolling summary for long conversations ─────────────
    op.add_column(
        "ai_chat_sessions",
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.add_column(
        "ai_chat_sessions",
        sa.Column(
            "summary_through_msg_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )

    # ── daily_nudges: one proactive FANI message per user per day ────────────
    op.create_table(
        "daily_nudges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nudge_date", sa.Date, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        # weather_outfit | new_arrival | unworn_pick | calendar_prep | streak | generic
        sa.Column("nudge_type", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("dismissed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_daily_nudges_user_date", "daily_nudges", ["user_id", "nudge_date"]
    )
    op.create_index(
        "ix_daily_nudges_user_date", "daily_nudges", ["user_id", "nudge_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_daily_nudges_user_date", table_name="daily_nudges")
    op.drop_constraint("uq_daily_nudges_user_date", "daily_nudges", type_="unique")
    op.drop_table("daily_nudges")
    op.drop_column("ai_chat_sessions", "summary_through_msg_count")
    op.drop_column("ai_chat_sessions", "summary")
