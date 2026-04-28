"""
Authentication endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.deps import DB, CurrentUser
from app.core.middleware import limiter
from app.core.config import settings
from app.schemas.auth import (
    AuthResponse,
    GoogleAuthRequest,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.schemas.user import MeResponse, UpdateMeRequest
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.services.cache_service import cache
from app.websockets.manager import ws_manager

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=AuthResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup(request: Request, body: SignupRequest, db: DB) -> AuthResponse:
    """Create a new account. Returns user info + token pair."""
    result = await AuthService.signup(db, body)

    # Broadcast login event to all connected clients
    await ws_manager.broadcast({
        "type": "user_joined",
        "username": result.user.username,
        "name": result.user.name,
    })

    return result


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(request: Request, body: LoginRequest, db: DB) -> AuthResponse:
    """Login with email/username + password."""
    result = await AuthService.login(db, body)

    # Broadcast login to all connected WS clients
    await ws_manager.broadcast({
        "type": "user_login",
        "username": result.user.username,
        "name": result.user.name,
    })

    return result


@router.post("/google", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def google_auth(request: Request, body: GoogleAuthRequest, db: DB) -> AuthResponse:
    """Exchange a Google/Firebase ID token for CLOZEHIVE tokens."""
    return await AuthService.google_login(db, body.id_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest, db: DB) -> TokenPair:
    """Exchange a refresh token for a new access + refresh token pair."""
    return await AuthService.refresh(db, body.refresh_token)


# ── Me endpoints (auth-aware, placed here for convenience) ───────────────────

@router.get("/me", response_model=MeResponse)
async def get_me(current_user: CurrentUser, db: DB) -> MeResponse:
    """Return the authenticated user's profile."""
    return await UserService.get_me(db, current_user.id)


@router.patch("/me", response_model=MeResponse)
async def update_me(body: UpdateMeRequest, current_user: CurrentUser, db: DB) -> MeResponse:
    """Update authenticated user's name, bio, or avatar_url."""
    return await UserService.update_me(db, current_user.id, body)
