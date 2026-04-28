"""
Auth routes — /api/v1/auth/*
Signup, login, refresh, logout, profile management.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services import cache_service
from app.repositories.user_repo import UserRepository
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/auth", tags=["Auth"])


def _svc(session: DbSession) -> AuthService:
    return AuthService(session)


# ── Public ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(body: SignupRequest, svc: AuthService = Depends(_svc)):
    """Create a new account. Returns user + token pair."""
    return await svc.signup(body)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, svc: AuthService = Depends(_svc)):
    """Authenticate with email/username + password."""
    return await svc.login(body.identifier, body.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, svc: AuthService = Depends(_svc)):
    """Exchange a valid refresh token for a new access + refresh pair (rotation)."""
    return await svc.refresh(body.refresh_token)


# ── Authenticated ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def me(user_id: CurrentUser, session: DbSession):
    """Return the currently authenticated user's profile."""
    users = UserRepository(session)
    user = await users.get_or_raise(__import__("uuid").UUID(user_id))
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user_id: CurrentUser,
    session: DbSession,
    bg: BackgroundTasks,
):
    """Update display name, bio, or avatar URL."""
    users = UserRepository(session)
    uid = __import__("uuid").UUID(user_id)
    user = await users.get_or_raise(uid)
    user = await users.update(
        user,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    )
    # Invalidate cache in background
    bg.add_task(cache_service.delete, cache_service.user_profile_key(user_id))
    return UserResponse.model_validate(user)


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    user_id: CurrentUser,
    svc: AuthService = Depends(_svc),
):
    """Change the authenticated user's password. Invalidates all sessions."""
    await svc.change_password(
        __import__("uuid").UUID(user_id),
        body.current_password,
        body.new_password,
    )


@router.post("/logout", status_code=204)
async def logout(
    body: RefreshRequest,
    user_id: CurrentUser,
    svc: AuthService = Depends(_svc),
):
    """Revoke the given refresh token."""
    await svc.logout(__import__("uuid").UUID(user_id), body.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_all(user_id: CurrentUser, svc: AuthService = Depends(_svc)):
    """Revoke ALL refresh tokens for the current user (sign out everywhere)."""
    await svc.logout_all(__import__("uuid").UUID(user_id))
