"""
Authentication endpoints.

Rate limits (via slowapi):
  /signup, /login, /google  →  10 requests / minute  (RATE_LIMIT_AUTH)
  /refresh                  →  30 requests / minute  (RATE_LIMIT_REFRESH)
  /logout, /logout-all      →  no limit (already authenticated)
  /change-password          →  10/minute  (same as login — prevents brute-force)
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.core.deps import DB, CurrentUser, CurrentUserID
from app.core.middleware import limiter
from app.core.config import settings
from app.core.security import generate_csrf_token
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.schemas.user import MeResponse, UpdateMeRequest
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.websockets.manager import ws_manager

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_csrf_cookie(response: Response) -> None:
    """
    Attach a CSRF token cookie to *response*.
    The cookie is readable by JS (not HttpOnly) so the client can echo it
    back in the X-CSRF-Token header.
    """
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,          # must be readable by JS
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        max_age=60 * 60 * 24 * 7,   # 7 days — matches refresh token TTL
    )


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup(
    request: Request,
    response: Response,
    body: SignupRequest,
    db: DB,
) -> AuthResponse:
    """
    Register a new account.

    Returns user profile + token pair. A CSRF cookie is also set so
    subsequent state-mutating requests can include the token in the header.
    """
    result = await AuthService.signup(db, body)
    _set_csrf_cookie(response)

    await ws_manager.broadcast({
        "type": "user_joined",
        "username": result.user.username,
        "name": result.user.name,
    })
    return result


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: DB,
) -> AuthResponse:
    """
    Login with email / username + password.

    On success resets failed-attempt counter and records last_login.
    On 5 consecutive failures the account is locked for 15 minutes.
    Returns 429 if the account is currently locked.
    """
    result = await AuthService.login(db, body)
    _set_csrf_cookie(response)

    await ws_manager.broadcast({
        "type": "user_login",
        "username": result.user.username,
        "name": result.user.name,
    })
    return result


@router.post("/google", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def google_auth(
    request: Request,
    response: Response,
    body: GoogleAuthRequest,
    db: DB,
) -> AuthResponse:
    """
    Exchange a Google Identity Services credential (ID token) for app tokens.

    The token's `aud` claim is validated against GOOGLE_CLIENT_ID.
    Returns 501 if GOOGLE_CLIENT_ID is not configured.
    """
    result = await AuthService.google_login(db, body.id_token)
    _set_csrf_cookie(response)
    return result


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings.RATE_LIMIT_REFRESH)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: DB,
) -> TokenPair:
    """
    Rotate a refresh token.

    The presented refresh token is immediately revoked and a new pair is issued.
    Rate-limited to 30/minute (tighter than login) to prevent token-grinding.
    """
    return await AuthService.refresh(db, body.refresh_token)


# ── Authenticated endpoints ───────────────────────────────────────────────────

@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    current_user: CurrentUser,
    db: DB,
) -> MessageResponse:
    """
    Revoke the current session's refresh token.

    Include the refresh_token in the request body so the server can revoke
    the exact token record. If omitted, the most-recent active session is
    revoked as a best-effort fallback.
    """
    return await AuthService.logout(db, current_user.id, body.refresh_token)


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    current_user: CurrentUser,
    db: DB,
) -> MessageResponse:
    """
    Revoke ALL active sessions for this account (log out from every device).
    Any access token currently in flight remains valid until it expires naturally
    (max ACCESS_TOKEN_EXPIRE_MINUTES minutes); after that every device must re-login.
    """
    return await AuthService.logout_all(db, current_user.id)


@router.post("/change-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DB,
) -> MessageResponse:
    """
    Change the authenticated user's password.

    Validates the current password first. On success, all existing refresh
    tokens are revoked so other sessions must re-authenticate.
    """
    return await AuthService.change_password(db, current_user.id, body)


# ── Profile (me) endpoints ────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
async def get_me(current_user: CurrentUser, db: DB) -> MeResponse:
    """Return the authenticated user's profile."""
    return await UserService.get_me(db, current_user.id)


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateMeRequest,
    current_user: CurrentUser,
    db: DB,
) -> MeResponse:
    """Update the authenticated user's name, bio, or avatar_url."""
    return await UserService.update_me(db, current_user.id, body)
