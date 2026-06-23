"""Add wear_events — append-only wear history.

closet_items.wear_count / last_worn are a destructive rollup (a counter + a
single date). They answer "how many times" and "most recently", but never
"when", so cost-per-wear-over-time, utilization windows, streaks, and the
weekly recap can't be reconstructed from them. This table is the source of
truth for time-series wear analytics; the rollup columns stay as a fast cache.

Backfill: seed one event per item that already has last_worn, so existing
"worn" items don't read as never-worn in the new utilization/forgotten-gem
views. We only know the *last* date, so a single event on that date is the
honest reconstruction.

Revision ID: 035
Revises: 034
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wear_events",
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
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("closet_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worn_on", sa.Date, nullable=False),
        # FK-free by design: may reference a planned_outfit or a saved outfit;
        # analytics only groups by it, never joins.
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Every analytics query filters by user and sorts/groups by date.
    op.create_index("ix_wear_events_user_worn", "wear_events", ["user_id", "worn_on"])
    # Per-item rollups (cost-per-wear, versatility joins) group by item.
    op.create_index("ix_wear_events_item", "wear_events", ["item_id"])

    # ── Backfill from the existing rollup ──────────────────────────────────────
    # One synthetic event per item that has a last_worn date. source='backfill'
    # so it's distinguishable from real logged wears in later analysis.
    op.execute(
        """
        INSERT INTO wear_events (id, user_id, item_id, worn_on, source, created_at)
        SELECT gen_random_uuid(), user_id, id, last_worn, 'backfill', now()
        FROM closet_items
        WHERE last_worn IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_wear_events_item", table_name="wear_events")
    op.drop_index("ix_wear_events_user_worn", table_name="wear_events")
    op.drop_table("wear_events")
