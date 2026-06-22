"""Add URL-paste source tracking to shopping_checks.

Lets "Shop with FANI" accept a product URL (OG/JSON-LD → screenshot fallback)
in addition to an uploaded photo, and instruments how the verdict was sourced
so we can measure repeat link-paste behaviour (the retention/viral signal).

Revision ID: 033
Revises: 032
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Where the analysed image came from: 'photo' (uploaded), 'url' (og/json-ld
    # product image) or 'screenshot' (rendered page fallback).
    op.add_column(
        "shopping_checks",
        sa.Column("input_type", sa.String(20), nullable=False, server_default="photo"),
    )
    # The product URL the user pasted (NULL for photo uploads). Source of truth
    # for the repeat-link instrumentation.
    op.add_column("shopping_checks", sa.Column("source_url", sa.Text, nullable=True))

    # Drives the "do they paste a 2nd/3rd link?" query: count url checks per user.
    op.create_index(
        "ix_shopping_checks_user_input_type",
        "shopping_checks",
        ["user_id", "input_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_shopping_checks_user_input_type", table_name="shopping_checks")
    op.drop_column("shopping_checks", "source_url")
    op.drop_column("shopping_checks", "input_type")
