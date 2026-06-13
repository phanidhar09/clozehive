"""Add closet_items.availability: laundry / cleaners / lent-out tracking.

Items marked anything other than 'available' are excluded from FANI's outfit
suggestions (generation, shuffle, pairings, weekly planner) until the user
marks them available again.

Revision ID: 031
Revises: 030
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "closet_items",
        sa.Column("availability", sa.String(20), nullable=False, server_default="available"),
    )


def downgrade() -> None:
    op.drop_column("closet_items", "availability")
