"""
Auth routes — /api/v1/auth/*
Signup, login, refresh, logout, profile management.
"""

from __future__ import annotations

from typing import Optional

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.security import build_google_auth_url
from app.repositories.user_repo import UserRepository
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
from app.services import cache_service
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()
logger = get_logger("auth_routes")

_OAUTH_STATE_PREFIX = "oauth:state:"
_OAUTH_STATE_TTL = 600  # 10 minutes


def _svc(session: DbSession) -> AuthService:
    return AuthService(session)


# ── Public ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=201)
@limiter.limit("3/minute")
async def signup(request: Request, body: SignupRequest, svc: AuthService = Depends(_svc)):
    """Create a new account. Returns user + token pair."""
    return await svc.signup(body)


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit("3/minute")
async def register(request: Request, body: SignupRequest, svc: AuthService = Depends(_svc)):
    """Alias for signup used by integration tests and API clients."""
    return await svc.signup(body)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, svc: AuthService = Depends(_svc)):
    """Authenticate with email/username + password."""
    return await svc.login(body.identifier, body.password)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, body: RefreshRequest, svc: AuthService = Depends(_svc)):
    """Exchange a valid refresh token for a new access + refresh pair (rotation)."""
    try:
        return await svc.refresh(body.refresh_token)
    except AuthenticationError as exc:
        if exc.message == "Refresh token has been revoked. Please log in again.":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)
        raise


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


@router.post("/logout")
async def logout(
    body: RefreshRequest | None = None,
    authorization: Optional[str] = Header(default=None),
    svc: AuthService = Depends(_svc),
):
    """Revoke the given refresh token."""
    refresh_token = body.refresh_token if body else None
    if not refresh_token and authorization and authorization.lower().startswith("bearer "):
        refresh_token = authorization.split(" ", 1)[1]
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token is required")
    await svc.logout_by_refresh(refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/logout-all", status_code=204)
async def logout_all(user_id: CurrentUser, svc: AuthService = Depends(_svc)):
    """Revoke ALL refresh tokens for the current user (sign out everywhere)."""
    await svc.logout_all(__import__("uuid").UUID(user_id))


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/login", include_in_schema=True, tags=["Auth"])
@limiter.limit("10/minute")
async def google_login(request: Request):
    """Redirect the browser to Google's OAuth consent screen."""
    if not settings.google_client_id or settings.google_client_id.strip().startswith(
        ("your-", "replace", "REPLACE")
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=501,
            content={
                "error": "OAUTH_NOT_CONFIGURED",
                "message": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the API .env",
            },
        )
    frontend = settings.frontend_url.rstrip("/")
    state = secrets.token_urlsafe(32)
    stored = await cache_service.set(_OAUTH_STATE_PREFIX + state, {"v": 1}, _OAUTH_STATE_TTL)
    if not stored:
        logger.error(
            "oauth_state_redis_failed",
            hint="OAuth requires Redis — check REDIS_URL and that Redis is reachable from the API",
        )
        return RedirectResponse(
            url=f"{frontend}/login?error=oauth_redis_unavailable",
            status_code=302,
        )
    return RedirectResponse(url=build_google_auth_url(state), status_code=302)


@router.get("/google/callback", include_in_schema=True, tags=["Auth"])
async def google_callback(
    request: Request,
    svc: AuthService = Depends(_svc),
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
):
    """Handle Google's redirect after OAuth consent. Issues JWT and redirects to the frontend."""
    frontend = settings.frontend_url.rstrip("/")

    # Diagnostics without OAuth codes in URLs
    logger.info(
        "google_oauth_callback_received",
        path=str(request.url.path),
        has_code=bool(code),
        has_state=bool(state),
        error=error,
    )

    # User denied consent or Google sent an error
    if error or not code or not state:
        logger.warning(
            "google_oauth_denied",
            error=error,
            has_error_description=bool(error_description),
            has_code=bool(code),
            has_state=bool(state),
        )
        if error == "redirect_uri_mismatch":
            return RedirectResponse(
                url=f"{frontend}/login?error=oauth_redirect_mismatch",
                status_code=302,
            )
        return RedirectResponse(
            url=f"{frontend}/login?error=oauth_cancelled",
            status_code=302,
        )

    # Validate CSRF state stored in Redis
    stored = await cache_service.get(_OAUTH_STATE_PREFIX + state)
    if not stored:
        logger.warning("google_oauth_invalid_state", state=state[:8])
        return RedirectResponse(
            url=f"{frontend}/login?error=oauth_invalid_state",
            status_code=302,
        )
    await cache_service.delete(_OAUTH_STATE_PREFIX + state)

    try:
        # Exchange authorisation code for Google access token
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        if token_resp.status_code != 200:
            try:
                detail = token_resp.json()
            except Exception:
                detail = token_resp.text[:500]
            logger.error(
                "google_token_exchange_failed",
                status_code=token_resp.status_code,
                detail=str(detail),
            )
            raise ValueError(f"Google token exchange failed ({token_resp.status_code}): {detail}")

        google_access_token = token_resp.json()["access_token"]

        # Fetch user profile from Google
        async with httpx.AsyncClient(timeout=10.0) as client:
            info_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {google_access_token}"},
            )
        if info_resp.status_code != 200:
            raise ValueError("Failed to fetch Google user profile")

        info = info_resp.json()
        google_id: str = info["id"]
        email: str = info.get("email", "")
        name: str = info.get("name") or (email.split("@")[0] if email else "User")
        avatar_url: Optional[str] = info.get("picture")

        if not email:
            raise ValueError("Google account has no email address")

        auth_result = await svc.google_oauth_login(google_id, email, name, avatar_url)

        params = urlencode({
            "access_token": auth_result.access_token,
            "refresh_token": auth_result.refresh_token,
        })
        return RedirectResponse(
            url=f"{frontend}/oauth/callback?{params}",
            status_code=302,
        )

    except Exception as exc:
        logger.error(
            "google_oauth_callback_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        hint = ""
        err_lower = str(exc).lower()
        if "redirect_uri_mismatch" in err_lower:
            hint = "&reason=redirect_uri_mismatch"
        elif "invalid_client" in err_lower:
            hint = "&reason=invalid_client"
        elif "failed" in err_lower and "token" in err_lower:
            hint = "&reason=token_exchange"
        return RedirectResponse(
            url=f"{frontend}/login?error=oauth_failed{hint}",
            status_code=302,
        )
