"""Add personalization profile columns to users.

Revision ID: 004
Revises: 003
Create Date: 2026-04-30

Adds five nullable JSONB columns used by the User Intelligence Hub:
  body_profile, style_profile, preferences, permissions, avatar_config

All columns are nullable so existing users keep working without backfill.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


_NEW_COLS = ("body_profile", "style_profile", "preferences", "permissions", "avatar_config")


def upgrade() -> None:
    for col in _NEW_COLS:
        op.add_column(
            "users",
            sa.Column(col, postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    for col in reversed(_NEW_COLS):
        op.drop_column("users", col)
