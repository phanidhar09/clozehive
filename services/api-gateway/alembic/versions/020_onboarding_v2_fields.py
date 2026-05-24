"""Add onboarding v2 fields to user_style_profiles.

Revision ID: 020
Revises: 019
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSONB arrays – default empty list
    op.add_column(
        "user_style_profiles",
        sa.Column(
            "styling_goals",
            JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column(
            "avoidances",
            JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column(
            "pattern_preferences",
            JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # AI-derived fields
    op.add_column(
        "user_style_profiles",
        sa.Column("style_archetype", sa.String(100), nullable=True),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column("recommendation_rules", JSONB, nullable=True),
    )
    op.add_column(
        "user_style_profiles",
        sa.Column("ai_stylist_context", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_style_profiles", "ai_stylist_context")
    op.drop_column("user_style_profiles", "recommendation_rules")
    op.drop_column("user_style_profiles", "style_archetype")
    op.drop_column("user_style_profiles", "pattern_preferences")
    op.drop_column("user_style_profiles", "avoidances")
    op.drop_column("user_style_profiles", "styling_goals")
