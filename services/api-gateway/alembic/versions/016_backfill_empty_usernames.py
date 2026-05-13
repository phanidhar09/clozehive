"""Backfill empty / null usernames and names for all existing users.

Every user must have a non-null, non-empty, unique username and name.
This migration is safe to run against a live database with existing data.

Steps
-----
1. Backfill ``name`` for any rows where it is NULL or empty string,
   using the email prefix as a human-readable fallback.
2. Backfill ``username`` for any rows where it is NULL or empty string,
   derived from the email prefix.
3. Resolve any duplicate usernames that may exist from legacy data by
   appending a short suffix taken from the row id.

Revision ID: 016
Revises: 015
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Backfill missing name ──────────────────────────────────────────────
    # Use the email prefix (everything before @) as the display name.
    op.execute(
        """
        UPDATE users
        SET    name = SPLIT_PART(email, '@', 1)
        WHERE  name IS NULL OR TRIM(name) = ''
        """
    )

    # ── 2. Backfill missing username ──────────────────────────────────────────
    # Derive from email prefix: lowercase, remove non-alphanumeric, truncate.
    op.execute(
        """
        UPDATE users
        SET    username = LOWER(REGEXP_REPLACE(SPLIT_PART(email, '@', 1), '[^a-zA-Z0-9_]', '', 'g'))
        WHERE  username IS NULL OR TRIM(username) = ''
        """
    )

    # If the regex produced an empty string (e.g. email like "123!@x.com"),
    # fall back to a deterministic slug from the row id.
    op.execute(
        """
        UPDATE users
        SET    username = 'user_' || SUBSTRING(REPLACE(id::text, '-', ''), 1, 8)
        WHERE  username IS NULL OR TRIM(username) = ''
        """
    )

    # ── 3. Resolve duplicate usernames ───────────────────────────────────────
    # Keep the *oldest* row's username as-is; append a short id suffix to the
    # newer duplicates so every row ends up with a unique value.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   username,
                   ROW_NUMBER() OVER (PARTITION BY username ORDER BY created_at ASC, id ASC) AS rn
            FROM   users
        )
        UPDATE users u
        SET    username = u.username || '_' || SUBSTRING(REPLACE(u.id::text, '-', ''), 1, 6)
        FROM   ranked r
        WHERE  u.id = r.id
          AND  r.rn > 1
        """
    )


def downgrade() -> None:
    # Backfill cannot be reversed safely; the downgrade is intentionally a no-op.
    pass
