"""Add packing_plans.user_edits: user-authored deltas over an AI packing plan.

The packing plan is almost entirely *derived* — packing_checklist,
take_from_your_closet, bag_capacity_summary and daily_plan are all recomputed
from ``day_plans_rich`` on every save. That means a user edit written straight
into any of those columns is erased the next time a plan is generated.

``user_edits`` is the durable delta layer that survives regeneration:

    {
      "pinned_days":      [3, 5],          # days the user edited — never re-planned
      "outfit_edits":     [ {...}, ... ],  # append-only audit log of item swaps
      "checklist_added":  [ {"closet_item_id": "...", "note": "..."} ],
      "checklist_removed":["<checklist key>", ...],
      "stale_notes":      ["3:evening", ...]  # outfits whose styling prose is outdated
    }

On regenerate, pinned days are spliced back over the fresh plan and the
checklist add/remove deltas are re-applied, so a user never loses hand-made
changes to a "Regenerate Plan" click.

Additive and reversible — existing rows default to an empty object, which
replays as "no edits" and reproduces today's behaviour exactly.

Revision ID: 039
Revises: 038
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "packing_plans",
        sa.Column(
            "user_edits",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("packing_plans", "user_edits")
