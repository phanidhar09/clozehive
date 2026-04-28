"""
FastAPI dependency injection helpers.

Usage examples:
    # Require any authenticated user
    @router.get("/me")
    async def get_me(user: CurrentUser): ...

    # Require ADMIN role
    @router.delete("/users/{id}")
    async def delete_user(user: CurrentUser, _: AdminOnly): ...

    # Require a specific role at call-site
    @router.post("/promote")
    async def promote(user: CurrentUser, _=Depends(require_role("admin"))): ...

    # Optional auth (public endpoint that enriches response for logged-in users)
    @router.get("/feed")
    async def feed(user_id: OptionalUserID): ...
"""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_token
from app.db.session import async_session_factory

_bearer = HTTPBearer(auto_error=False)


# ── Database session ──────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session; auto-commit on success, rollback on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_db)]


# ── Token extraction ──────────────────────────────────────────────────────────

async def _get_token_payload(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Extract and decode the Bearer token; raises 401 on any failure."""
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


# ── Full user object ──────────────────────────────────────────────────────────
# Lazy-imported to avoid circular dependencies at module load time.

def _get_user_service():
    from app.services.user_service import UserService  # noqa: PLC0415
    return UserService


async def get_current_user(user_id: CurrentUserID, db: DB):
    """Return full User ORM object; raises 401 if the account was deleted."""
    UserService = _get_user_service()
    user = await UserService.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    return user


from app.models.user import User, UserRole  # noqa: E402

CurrentUser = Annotated[User, Depends(get_current_user)]


# ── RBAC ──────────────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    Dependency factory for role-based access control.

    Usage::

        @router.delete("/users/{id}")
        async def delete_user(
            user: CurrentUser,
            _=Depends(require_role("admin")),
        ): ...

    Multiple roles are accepted with OR semantics (user must have at least one).
    """
    allowed = {r.lower() for r in roles}

    async def _check(user: CurrentUser):
        user_role = (user.role.value if user.role else "user").lower()
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {', '.join(sorted(allowed))}",
            )
        return user

    return _check


# Convenience shortcuts
AdminOnly = Annotated[User, Depends(require_role("admin"))]
"""Require the current user to have the 'admin' role."""


# ── Optional auth ─────────────────────────────────────────────────────────────

async def get_optional_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int | None:
    """
    Like get_current_user_id but returns None instead of raising 401.
    Use for public endpoints that optionally personalise for logged-in users.
    """
    if creds is None:
        return None
    try:
        payload = decode_token(creds.credentials, expected_type="access")
        return int(payload["sub"])
    except (TokenError, ValueError):
        return None


OptionalUserID = Annotated[int | None, Depends(get_optional_user_id)]
