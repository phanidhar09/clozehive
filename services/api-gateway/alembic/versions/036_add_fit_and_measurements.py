"""Add closet_items.fit + measurements — structured size foundation.

A bare size label ("M") is meaningless across brands and fits: a slim-M and a
relaxed-M are different garments, and "M" in one brand equals "S" in another.
These two columns are step one of resolving size into something brand-agnostic:

- ``fit``: slim / regular / relaxed / oversized / tailored. The vision pipeline
  already *detects* fit (VisionAnalysisItem.fit) but there was nowhere to store
  it, so it was dropped at save time. This column stops that data loss.
- ``measurements``: canonical garment measurements in cm (chest/waist/inseam/
  length) as JSONB. Null until resolved from a brand size chart or user input
  (Phase 2). JSONB rather than 4 sparse numeric columns since it's optional and
  the key set varies by category.

Both are nullable and additive — no backfill, fully reversible.

Revision ID: 036
Revises: 035
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("closet_items", sa.Column("fit", sa.String(30), nullable=True))
    op.add_column(
        "closet_items",
        sa.Column("measurements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("closet_items", "measurements")
    op.drop_column("closet_items", "fit")
