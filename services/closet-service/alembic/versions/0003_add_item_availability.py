"""Add closet_items.availability: laundry / cleaners / lent-out tracking.

Mirror of api-gateway migration 031. Items marked anything other than
'available' are excluded from FANI's outfit suggestions until the user marks
them available again.

Revision ID: 0003_item_availability
Revises: 0002_planned_outfits
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_item_availability"
down_revision: Union[str, None] = "0002_planned_outfits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "closet_items",
        sa.Column("availability", sa.String(20), nullable=False, server_default="available"),
    )


def downgrade() -> None:
    op.drop_column("closet_items", "availability")
