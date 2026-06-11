"""Username generation and normalisation utilities."""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_username(value: str) -> str:
    """Derive a clean username slug from any display-name or email prefix.

    Rules (matching spec examples):
    - Lowercase
    - Remove spaces entirely  ("Phanidhar Reddy" → "phanidharreddy")
    - Strip all chars except a-z, 0-9, underscore
    - Collapse repeated underscores, strip leading/trailing underscores
    - Truncate to 30 characters
    - Never return empty string — fallback is "user"
    """
    value = value.lower().strip()
    value = value.replace(" ", "")  # remove spaces (not → underscore)
    value = re.sub(r"[^a-z0-9_]", "", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:30] or "user"


async def username_exists(session: AsyncSession, username: str) -> bool:
    """Return True if *username* is already taken in the users table."""
    from app.models.user import User  # local import to avoid circular dependency

    result = await session.execute(select(func.count()).select_from(User).where(User.username == username))
    return result.scalar_one() > 0


async def generate_unique_username(
    session: AsyncSession,
    base_name: str = "",
    fallback_email: str = "",
    *,
    exclude_id: str | None = None,
) -> str:
    """Derive a unique username from a display name or email.

    1. Normalise ``base_name`` (full name / Google display name).
    2. If that is empty or just "user", fall back to the email prefix.
    3. Append an incrementing counter until a free slot is found:
       phani → phani1 → phani2 …

    ``exclude_id`` can be set to the current user's UUID string so that
    a user's *own* existing username is not counted as a collision when
    generating a replacement for them.
    """
    from app.models.user import User  # local import

    base = normalize_username(base_name)
    if not base or base == "user":
        base = normalize_username(fallback_email.split("@")[0]) if fallback_email else "user"
    if not base:
        base = "user"

    async def _taken(username: str) -> bool:
        stmt = select(func.count()).select_from(User).where(User.username == username)
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        result = await session.execute(stmt)
        return result.scalar_one() > 0

    username = base
    counter = 1
    while await _taken(username):
        username = f"{base}{counter}"
        counter += 1
    return username
