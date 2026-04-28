"""
FastAPI dependency injection helpers.

Usage:
    @router.get("/me")
    async def get_me(user: CurrentUser):
        ...
"""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_token
from app.db.session import async_session_factory

_bearer = HTTPBearer(auto_error=False)


# ── Database session ─────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, auto-commit / rollback on exit."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_db)]


# ── Authentication ───────────────────────────────────────────────────────────

async def _get_token_payload(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(creds.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_id(
    payload: dict = Depends(_get_token_payload),
) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")


CurrentUserID = Annotated[int, Depends(get_current_user_id)]


# ── Lazy import to avoid circular deps ──────────────────────────────────────

def _get_user_service():
    from app.services.user_service import UserService  # noqa: PLC0415
    return UserService


async def get_current_user(
    user_id: CurrentUserID,
    db: DB,
):
    """Return full User ORM object; raises 401 if not found (deleted account)."""
    UserService = _get_user_service()
    user = await UserService.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    return user


from app.models.user import User  # noqa: E402 (needed for Annotated type)

CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Optional auth (for public endpoints that enhance for logged-in users) ───

async def get_optional_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int | None:
    if creds is None:
        return None
    try:
        payload = decode_token(creds.credentials, expected_type="access")
        return int(payload["sub"])
    except (TokenError, ValueError):
        return None


OptionalUserID = Annotated[int | None, Depends(get_optional_user_id)]
