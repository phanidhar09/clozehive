"""Add closet_items.condition: physical wear state for occasion-aware styling.

Distinct from ``availability`` (which tracks *where* an item is). ``condition``
tracks *what state* it's in — new / excellent / good / fair / worn / damaged —
and is ordinal (see app.constants.wardrobe.CONDITION_RANK).

Unlike availability, condition is a *soft* styling signal: a WORN item is still
suggested for casual/beach occasions and only demoted for formal ones. The one
exception is DAMAGED, which later steps hard-exclude from styling and packing.

Additive and reversible. Existing rows default to 'good' (the neutral middle of
the scale, which passes the formal floor) so no item is wrongly demoted before a
user has ever set a real condition.

Revision ID: 037
Revises: 036
Create Date: 2026-07-08
"""

import sqlalchemy as sa

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "closet_items",
        sa.Column("condition", sa.String(20), nullable=False, server_default="good"),
    )


def downgrade() -> None:
    op.drop_column("closet_items", "condition")
