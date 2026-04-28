"""
FastAPI dependency injection — reusable dependencies for all routes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ForbiddenError
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


async def get_current_admin(
    user_id: Annotated[str, Depends(get_current_user_id)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Like get_current_user_id but also checks role == 'admin'."""
    try:
        payload = decode_access_token(credentials.credentials)
        if payload.get("role") != "admin":
            raise ForbiddenError("Admin access required")
        return user_id
    except (JWTError, KeyError):
        raise AuthenticationError("Invalid or expired token")


# ── Type aliases for clean route signatures ───────────────────────────────────

CurrentUser = Annotated[str, Depends(get_current_user_id)]
AdminUser = Annotated[str, Depends(get_current_admin)]
