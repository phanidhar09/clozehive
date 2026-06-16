"""Internal (service-to-service) endpoints — not exposed to browsers.

Protected by the shared ``INTERNAL_SERVICE_TOKEN`` (``X-Internal-Token`` header).
Mounted at ``/internal`` (outside ``/api/v1``).

``GET /internal/users/{user_id}`` lets closet-service read the few legacy User
profile fields it needs for styling (it does NOT own the users table). See
closet-service ``repositories/user_repo.py`` for the consumer side.
"""

from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Header

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.exceptions import AuthenticationError, NotFoundError

router = APIRouter(prefix="/internal", tags=["internal"])
settings = get_settings()


def _verify_internal_token(x_internal_token: str | None) -> None:
    expected = settings.internal_service_token
    # Fail closed: refuse if no token is configured rather than allow-all.
    # Constant-time compare so response timing cannot leak the token byte-by-byte.
    if not expected or not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise AuthenticationError("Invalid internal service token")


@router.get("/users/{user_id}")
async def get_user(
    user_id: UUID,
    session: DbSession,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, object | None]:
    """Return the profile fields closet-service styling reads. Internal only."""
    _verify_internal_token(x_internal_token)
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise NotFoundError("User not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "permissions": user.permissions,
        "body_profile": user.body_profile,
        "style_profile": user.style_profile,
        "preferences": user.preferences,
    }
