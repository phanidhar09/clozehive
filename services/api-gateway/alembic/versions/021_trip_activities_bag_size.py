"""Add activities, bag_size, trip_style to trips; enrich packing_plans.

Revision ID: 021
Revises: 020
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── trips ────────────────────────────────────────────────────────────────
    op.add_column("trips", sa.Column("trip_style", sa.String(50), nullable=True))
    op.add_column("trips", sa.Column("bag_size", sa.String(50), nullable=True))
    op.add_column(
        "trips",
        sa.Column(
            "activities",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # ── packing_plans ─────────────────────────────────────────────────────────
    op.add_column("packing_plans", sa.Column("activities", postgresql.JSONB, nullable=True))
    op.add_column("packing_plans", sa.Column("day_plans_rich", postgresql.JSONB, nullable=True))
    op.add_column("packing_plans", sa.Column("rewear_strategy", postgresql.JSONB, nullable=True))
    op.add_column("packing_plans", sa.Column("bag_capacity_summary", postgresql.JSONB, nullable=True))
    op.add_column("packing_plans", sa.Column("packing_checklist", postgresql.JSONB, nullable=True))
    op.add_column("packing_plans", sa.Column("checklist_state", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("packing_plans", "checklist_state")
    op.drop_column("packing_plans", "packing_checklist")
    op.drop_column("packing_plans", "bag_capacity_summary")
    op.drop_column("packing_plans", "rewear_strategy")
    op.drop_column("packing_plans", "day_plans_rich")
    op.drop_column("packing_plans", "activities")
    op.drop_column("trips", "activities")
    op.drop_column("trips", "bag_size")
    op.drop_column("trips", "trip_style")
