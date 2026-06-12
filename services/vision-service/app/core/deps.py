"""
FastAPI dependency injection for vision-service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.db.session import get_session

# ── DB session ────────────────────────────────────────────────────────────────

DbSession = Annotated[AsyncSession, Depends(get_session)]

# ── JWT bearer ────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """
    Validate the JWT Bearer token and return the user_id (sub claim).
    Raises AuthenticationError if token is absent, malformed, or expired.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload["sub"]
        return user_id
    except (JWTError, KeyError, TypeError):
        raise AuthenticationError("Invalid or expired token")


# ── Type alias for clean route signatures ─────────────────────────────────────

CurrentUser = Annotated[str, Depends(get_current_user_id)]
