"""Add auth_provider column to users table.

Revision ID: 015
Revises: 014
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column with a server default so existing rows are handled atomically
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(20),
            nullable=False,
            server_default="local",
        ),
    )
    # Backfill: any user that has a google_id is a Google-auth user
    op.execute(
        "UPDATE users SET auth_provider = 'google' WHERE google_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "auth_provider")
