"""Add skin_tone + undertone to user_style_profiles for colour-aware recommendations.

Revision ID: 027
Revises: 026
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_style_profiles",
        sa.Column("skin_tone", sa.String(32), nullable=True),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column("undertone", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_style_profiles", "undertone")
    op.drop_column("user_style_profiles", "skin_tone")
