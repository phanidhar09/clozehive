"""Drop redundant standalone indexes on planned_outfits.

The unique constraint ``uq_planned_outfits_user_date`` already provides a
composite btree index on ``(user_id, plan_date)``. That composite serves every
planner access pattern in the codebase:

  - ``WHERE user_id = ? AND plan_date BETWEEN ? AND ?``  (get/generate week)
  - ``WHERE user_id = ? AND plan_date = ?``              (set/clear/worn day)
  - ``WHERE user_id = ?``                                (leading-column prefix)

So ``idx_planned_outfits_user_id`` is fully redundant with the composite (a
btree on (user_id, plan_date) answers user_id-prefixed lookups), and no query
filters by ``plan_date`` alone, leaving ``idx_planned_outfits_plan_date`` as
pure write/storage overhead. Drop both; the composite stays via the unique
constraint.

Idempotent (DROP INDEX IF EXISTS) so it is safe to run against a DB where the
indexes were never created.

Revision ID: 032
Revises: 031
Create Date: 2026-06-15
"""

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_planned_outfits_user_id")
    op.execute("DROP INDEX IF EXISTS idx_planned_outfits_plan_date")


def downgrade() -> None:
    op.create_index("idx_planned_outfits_plan_date", "planned_outfits", ["plan_date"])
    op.create_index("idx_planned_outfits_user_id", "planned_outfits", ["user_id"])
