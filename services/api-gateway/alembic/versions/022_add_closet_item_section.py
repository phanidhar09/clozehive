"""Add section column to closet_items.

Revision ID: 022
Revises: 021
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "closet_items",
        sa.Column("section", sa.String(50), nullable=True),
    )
    op.create_index("ix_closet_items_section", "closet_items", ["section"])


def downgrade() -> None:
    op.drop_index("ix_closet_items_section", table_name="closet_items")
    op.drop_column("closet_items", "section")
