"""Add query performance indexes.

Revision ID: 006
Revises: 005
Create Date: 2026-05-01
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_closet_items_user_id ON closet_items (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_closet_items_category ON closet_items (category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_closet_items_created_at ON closet_items (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trips_user_id ON trips (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outfits_user_id ON outfits (user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outfits_user_id")
    op.execute("DROP INDEX IF EXISTS ix_trips_user_id")
    op.execute("DROP INDEX IF EXISTS ix_closet_items_created_at")
    op.execute("DROP INDEX IF EXISTS ix_closet_items_category")
    op.execute("DROP INDEX IF EXISTS ix_closet_items_user_id")
