"""Add style_summary column to user_style_profiles.

Stores an AI-generated natural-language summary of the user's style preferences.
Generated automatically when the user saves or completes their style profile.
Used as context in all AI prompts (outfit suggestions, packing, chat).

Revision ID: 017
Revises: 016
Create Date: 2026-05-12
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_style_profiles",
        sa.Column("style_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_style_profiles", "style_summary")
