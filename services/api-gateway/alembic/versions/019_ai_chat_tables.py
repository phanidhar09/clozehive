"""Add AI Stylist Chat tables: ai_chat_sessions, ai_chat_messages, outfit_feedback.

Revision ID: 019
Revises: 018
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ai_chat_sessions ─────────────────────────────────────────────────────
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ai_chat_sessions_user_id", "ai_chat_sessions", ["user_id"])
    op.create_index("ix_ai_chat_sessions_created_at", "ai_chat_sessions", ["created_at"])

    # ── ai_chat_messages ─────────────────────────────────────────────────────
    op.create_table(
        "ai_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("structured_response", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ai_chat_messages_session_id", "ai_chat_messages", ["session_id"])
    op.create_index("ix_ai_chat_messages_user_id", "ai_chat_messages", ["user_id"])
    op.create_index("ix_ai_chat_messages_created_at", "ai_chat_messages", ["created_at"])

    # ── outfit_feedback ──────────────────────────────────────────────────────
    op.create_table(
        "outfit_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "outfit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfits.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("closet_item_ids", postgresql.JSONB, nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("feedback_text", sa.Text, nullable=True),
        sa.Column("occasion", sa.String(100), nullable=True),
        sa.Column("mood", sa.String(100), nullable=True),
        sa.Column("was_worn", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_outfit_feedback_user_id", "outfit_feedback", ["user_id"])
    op.create_index("ix_outfit_feedback_outfit_id", "outfit_feedback", ["outfit_id"])
    op.create_index("ix_outfit_feedback_occasion", "outfit_feedback", ["occasion"])
    op.create_index("ix_outfit_feedback_created_at", "outfit_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("outfit_feedback")
    op.drop_table("ai_chat_messages")
    op.drop_table("ai_chat_sessions")
