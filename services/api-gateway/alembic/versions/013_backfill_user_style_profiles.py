"""Backfill user_style_profiles for existing users (completed onboarding).

Revision ID: 013
Revises: 012
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO user_style_profiles (
                id, user_id,
                body_types, fit_preferences, size_profile, style_preferences,
                favorite_colors, avoided_colors, occasion_preferences, climate_preferences,
                onboarding_completed, onboarding_skipped,
                created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                u.id,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb,
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                true, false,
                NOW(), NOW()
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM user_style_profiles p WHERE p.user_id = u.id
            )
            """
        )
    )


def downgrade() -> None:
    # Cannot safely remove only backfilled rows — no-op.
    pass
