"""Add item_pair_scores: the derived affinity rollup that closes the feedback loop.

ClozeHive already *captures* outfit feedback (``outfit_feedback`` — rating,
was_worn, closet_item_ids) and wear history (``wear_events``), and the
``/feedback`` endpoint even tells the user it "improves future recommendations".
Until now nothing read those signals, so that promise was a no-op.

This table is the missing derived layer: one row per unordered pair of a user's
closet items, holding a running affinity accumulator updated incrementally from
feedback. The outfit builder reads it to softly re-rank looks toward pairings the
user has actually accepted/worn — a bounded tie-breaker, never a filter (see
``app.core.pair_learning`` and ``outfit_builder._pair_learning_factor``).

Canonical ordering (``item_a < item_b``) plus the unique constraint mean each
unordered pair maps to exactly one row, so writes are a single ``ON CONFLICT``
upsert with no read-modify-write race.

Additive and reversible — an empty table replays as "no learned signal", which
reproduces today's builder output exactly (every pair contributes neutral 0).

Revision ID: 040
Revises: 038
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "040"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_pair_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_a",
            UUID(as_uuid=True),
            sa.ForeignKey("closet_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_b",
            UUID(as_uuid=True),
            sa.ForeignKey("closet_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Running accumulator (can be negative). The bounded affinity the builder
        # consumes is derived from this at read time, never stored.
        sa.Column("raw_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "last_signal_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "item_a", "item_b", name="uq_item_pair_scores_user_pair"),
    )
    # The builder loads every pair among a closet's items for one user in a single
    # query; this index serves that lookup.
    op.create_index("ix_item_pair_scores_user", "item_pair_scores", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_item_pair_scores_user", table_name="item_pair_scores")
    op.drop_table("item_pair_scores")
