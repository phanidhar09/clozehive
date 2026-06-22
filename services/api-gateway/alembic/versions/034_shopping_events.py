"""Add shopping_events — instrument the Shop with FANI funnel.

Every paste should log what the user did next: viewed the verdict, opened the
outfit, acted on it, or pasted again. This is the cheapest retention experiment
we have, so the measurement is built in from the start rather than bolted on.

Revision ID: 034
Revises: 033
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nullable so funnel events not tied to a specific check (or whose check
        # was deleted) still record. SET NULL keeps the event for analytics.
        sa.Column(
            "check_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shopping_checks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_shopping_events_user_created", "shopping_events", ["user_id", "created_at"])
    op.create_index("ix_shopping_events_check", "shopping_events", ["check_id"])
    op.create_index("ix_shopping_events_type", "shopping_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_shopping_events_type", table_name="shopping_events")
    op.drop_index("ix_shopping_events_check", table_name="shopping_events")
    op.drop_index("ix_shopping_events_user_created", table_name="shopping_events")
    op.drop_table("shopping_events")
