"""Change closet_items.season from String(50) to ARRAY(String).

A garment can belong to multiple seasons (e.g. spring/summer), so the column
is widened from a single VARCHAR to VARCHAR[].

Data preservation
-----------------
Upgrade:   NULL       → NULL
           ""         → NULL
           "summer"   → ARRAY['summer']

Downgrade: NULL / {}  → NULL
           ARRAY[…]   → first element (VARCHAR(50))

Revision ID: 009
Revises: 008
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE closet_items
        ALTER COLUMN season TYPE VARCHAR[]
        USING CASE
            WHEN season IS NULL OR trim(season) = '' THEN NULL
            ELSE ARRAY[season]
        END
    """))


def downgrade() -> None:
    # Collapse array back to a single VARCHAR(50): keep only the first element.
    op.execute(sa.text("""
        ALTER TABLE closet_items
        ALTER COLUMN season TYPE VARCHAR(50)
        USING CASE
            WHEN season IS NULL
              OR array_length(season, 1) IS NULL
              OR array_length(season, 1) = 0
            THEN NULL
            ELSE season[1]
        END
    """))
