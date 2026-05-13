"""User style profiles for onboarding and AI personalization.

Revision ID: 012
Revises: 011
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_style_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gender", sa.String(32), nullable=True),
        sa.Column("custom_gender", sa.String(120), nullable=True),
        sa.Column("height_value", sa.Numeric(6, 2), nullable=True),
        sa.Column("height_unit", sa.String(8), nullable=True),
        sa.Column("weight_value", sa.Numeric(7, 2), nullable=True),
        sa.Column("weight_unit", sa.String(8), nullable=True),
        sa.Column("age_range", sa.String(32), nullable=True),
        sa.Column("body_types", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custom_body_type", sa.String(200), nullable=True),
        sa.Column("fit_preferences", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custom_fit_notes", sa.String(500), nullable=True),
        sa.Column("size_profile", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("custom_size_notes", sa.String(500), nullable=True),
        sa.Column("style_preferences", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("favorite_colors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("avoided_colors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("neutral_color_preference", sa.Boolean(), nullable=True),
        sa.Column("bold_color_preference", sa.Boolean(), nullable=True),
        sa.Column(
            "occasion_preferences", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "climate_preferences", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "onboarding_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_style_profiles_user_id",
        "user_style_profiles",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_style_profiles_user_id", table_name="user_style_profiles")
    op.drop_table("user_style_profiles")
