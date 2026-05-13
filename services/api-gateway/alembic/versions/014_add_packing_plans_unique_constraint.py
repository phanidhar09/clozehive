"""Add unique constraint on packing_plans(trip_id, user_id).

Revision ID: 014
Revises: 013
Create Date: 2026-05-08
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_packing_plans_trip_user",
        "packing_plans",
        ["trip_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_packing_plans_trip_user",
        "packing_plans",
        type_="unique",
    )
