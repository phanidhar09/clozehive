"""
Auth routes — /api/v1/auth/*
Signup, login, refresh, logout, profile management.

Refresh-token cookie strategy
──────────────────────────────
The refresh token is **never** sent in the response body. Instead, every
endpoint that issues a new refresh token calls ``_set_refresh_cookie()`` on
the ``Response`` object.  The frontend must include ``withCredentials: true``
(axios) / ``credentials: "include"`` (fetch) on all calls to /auth/refresh and
/auth/logout so the browser sends the HttpOnly cookie automatically.

This eliminates the XSS token-theft surface: even a full XSS payload cannot
read or exfiltrate the refresh token because it lives only in the cookie jar.
"""

from __future__ import annotations

import secrets
import uuid as _uuid
from typing import Optional
from urllib.parse import urlencode

from pydantic import BaseModel

import httpx
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.security import build_google_auth_url
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
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
_OAUTH_CODE_PREFIX = "oauth:tokens:"
_OAUTH_CODE_TTL = 120  # 2 minutes — single-use exchange window


def _oauth_login_redirect(
    frontend: str,
    *,
    error: str,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
) -> str:
    """Build a safe frontend login redirect URL with optional OAuth reason/detail.

    ``detail`` carries a short, sanitised error string for debugging and is only
    populated when ``OAUTH_DEBUG_ERRORS`` is enabled (never in normal production).
    """
    params: dict[str, str] = {"error": error}
    if reason:
        params["reason"] = reason
    if detail:
        # Cap length and strip newlines so the URL stays clean and bounded.
        params["detail"] = " ".join(str(detail).split())[:200]
    return f"{frontend}/login?{urlencode(params)}"


# ── HttpOnly cookie helpers ───────────────────────────────────────────────────

_REFRESH_COOKIE_NAME = "ch_refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the HttpOnly refresh-token cookie on *response*.

    Security properties:
      - HttpOnly     : JavaScript cannot read the cookie (XSS protection).
      - Secure       : Only sent over HTTPS (enforced in production).
      - SameSite=Lax : Sent on top-level navigations but NOT on cross-site
                       sub-resource requests (CSRF mitigation).
      - Max-Age      : Aligned with the server-side token TTL.
    """
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,      # True in production
        samesite=settings.cookie_samesite,  # "Lax" default
        max_age=max_age,
        path="/api/v1/auth",               # Scope cookie to auth paths only
        domain=settings.cookie_domain or None,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Expire the refresh-token cookie immediately."""
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        domain=settings.cookie_domain or None,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _svc(session: DbSession) -> AuthService:
    return AuthService(session)


# ── Public ────────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse, status_code=201)
@limiter.limit("3/minute")
async def signup(request: Request, response: Response, body: SignupRequest, svc: AuthService = Depends(_svc)):
    """Create a new account.

    Returns user + access token in body; refresh token is set as HttpOnly cookie.
    """
    auth, refresh_raw = await svc.signup(body)
    _set_refresh_cookie(response, refresh_raw)
    return auth


@router.post("/register", response_model=AuthResponse, status_code=201)
@limiter.limit("3/minute")
async def register(request: Request, response: Response, body: SignupRequest, svc: AuthService = Depends(_svc)):
    """Alias for signup used by integration tests and API clients."""
    auth, refresh_raw = await svc.signup(body)
    _set_refresh_cookie(response, refresh_raw)
    return auth


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, body: LoginRequest, svc: AuthService = Depends(_svc)):
    """Authenticate with email/username + password.

    Returns user + access token in body; refresh token is set as HttpOnly cookie.
    """
    auth, refresh_raw = await svc.login(body.identifier, body.password)
    _set_refresh_cookie(response, refresh_raw)
    return auth


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    # Read refresh token from HttpOnly cookie (preferred path).
    # Fall back to body field for backwards compatibility with old clients.
    ch_refresh_token: Optional[str] = Cookie(default=None),
    body: RefreshRequest = RefreshRequest(),
    svc: AuthService = Depends(_svc),
):
    """Rotate the refresh token.

    Reads the refresh token from the HttpOnly cookie.  Clients must send
    requests with ``withCredentials: true`` / ``credentials: "include"``.
    Legacy clients may still send the token in the request body.
    """
    raw_token = ch_refresh_token or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided. Include credentials or send token in body.",
        )
    try:
        new_access, new_refresh_raw = await svc.refresh(raw_token)
    except AuthenticationError as exc:
        _clear_refresh_cookie(response)
        if "revoked" in exc.message.lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message)
        raise
    _set_refresh_cookie(response, new_refresh_raw)
    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ── Authenticated ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def me(user_id: CurrentUser, session: DbSession):
    """Return the currently authenticated user's profile."""
    users = UserRepository(session)
    user = await users.get_or_raise(_uuid.UUID(user_id))
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user_id: CurrentUser,
    session: DbSession,
    bg: BackgroundTasks,
):
    """Update display name, username, bio, avatar URL, or personalization data."""
    users = UserRepository(session)
    uid = _uuid.UUID(user_id)
    user = await users.get_or_raise(uid)

    update_kwargs = {k: v for k, v in body.model_dump().items() if v is not None}

    # Username uniqueness check — only enforce if it actually changed
    if "username" in update_kwargs and update_kwargs["username"] != user.username:
        if await users.username_exists(update_kwargs["username"]):
            raise ConflictError("Username is already taken")

    user = await users.update(user, **update_kwargs)
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
        _uuid.UUID(user_id),
        body.current_password,
        body.new_password,
    )


# ── Password reset ─────────────────────────────────────────────────────────────

@router.post("/forgot-password", status_code=202)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    svc: AuthService = Depends(_svc),
):
    """Send a password reset link to the given email address.

    Always returns 202 regardless of whether the email exists — this prevents
    account-enumeration attacks.  The frontend must show a generic success
    message like "If that email exists, a reset link has been sent."

    NOTE: This endpoint calls ``request_password_reset`` which returns the raw
    token.  In production, **send it by email** instead of logging it.  The
    token is intentionally not returned in the response body.
    """
    raw_token = await svc.request_password_reset(body.email)

    if raw_token:
        # TODO: replace with a real email delivery service (SendGrid, SES, etc.)
        # For now, log at DEBUG level so the token is visible in local dev logs.
        # In production, set LOG_LEVEL=INFO and this will be suppressed.
        logger.debug(
            "password_reset_token_issued",
            email=body.email,
            # REMOVE the token from the log before going to production!
            token_preview=raw_token[:8] + "…",
        )
        # Construct the reset URL using the configured frontend URL.
        reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
        logger.info("password_reset_link_generated", reset_url_length=len(reset_url))
        # ── email delivery placeholder ────────────────────────────────────────
        # await email_service.send_password_reset(email=body.email, reset_url=reset_url)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", status_code=204)
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    svc: AuthService = Depends(_svc),
):
    """Consume a reset token and set a new password.

    Returns 204 on success.  Returns 400/401 if the token is invalid, expired,
    or already used.  Returns a *generic* error message — does not reveal
    whether the token was valid.
    """
    try:
        await svc.reset_password(body.token, body.new_password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        )


@router.post("/logout")
async def logout(
    response: Response,
    # Cookie path (preferred — HttpOnly, never exposed to JS)
    ch_refresh_token: Optional[str] = Cookie(default=None),
    body: Optional[RefreshRequest] = None,
    authorization: Optional[str] = Header(default=None),
    svc: AuthService = Depends(_svc),
):
    """Revoke the refresh token and clear the HttpOnly cookie.

    Token resolution order:
      1. HttpOnly cookie (preferred).
      2. Request body ``refresh_token`` field (legacy clients).
      3. Authorization: Bearer header (last resort).
    """
    refresh_token = (
        ch_refresh_token
        or (body.refresh_token if body and body.refresh_token else None)
        or (authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None)
    )
    # Always clear the cookie even if the token lookup fails.
    _clear_refresh_cookie(response)
    if not refresh_token:
        # No token to revoke — cookie already cleared, just return success.
        return {"message": "Logged out successfully"}
    await svc.logout_by_refresh(refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/logout-all", status_code=204)
async def logout_all(user_id: CurrentUser, svc: AuthService = Depends(_svc)):
    """Revoke ALL refresh tokens for the current user (sign out everywhere)."""
    await svc.logout_all(_uuid.UUID(user_id))


# ── GDPR endpoints ────────────────────────────────────────────────────────────

async def _cleanup_user_uploads(image_urls: list[str], user_id: str) -> None:
    """Background task: delete all GCS / local-disk uploads for a user.

    Runs *after* the DB row has been committed so the FK references are gone.
    Errors are logged but never re-raised — upload cleanup must not roll back the
    account deletion.
    """
    from app.services.upload_service import delete_upload

    deleted = 0
    failed = 0
    for url in image_urls:
        try:
            await delete_upload(url)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "upload_cleanup_failed",
                user_id=user_id,
                url=url[:80],
                error=str(exc),
            )
    logger.info(
        "upload_cleanup_complete",
        user_id=user_id,
        deleted=deleted,
        failed=failed,
    )


@router.delete("/me", status_code=204)
async def delete_account(
    user_id: CurrentUser,
    session: DbSession,
    bg: BackgroundTasks,
    svc: AuthService = Depends(_svc),
):
    """Permanently erase the authenticated user's account and all associated data (GDPR Art. 17).

    Upload cleanup (GCS / local disk) runs in a background task *after* the DB
    commit so it never blocks the response and cannot prevent the deletion if
    the storage layer is temporarily unavailable.
    """
    from sqlalchemy import select
    from app.models.closet import ClosetItem

    uid = _uuid.UUID(user_id)
    # Revoke all sessions before deletion so any cached tokens become invalid
    await svc.logout_all(uid)

    # Collect image URLs *before* deleting the user row (CASCADE will wipe them).
    # Deduplicate to avoid redundant GCS calls for shared blobs.
    closet_items = (await session.execute(
        select(ClosetItem.image_url, ClosetItem.original_image_url, ClosetItem.processed_image_url)
        .where(ClosetItem.user_id == uid)
    )).all()

    image_urls: list[str] = list({
        url
        for row in closet_items
        for url in (row.image_url, row.original_image_url, row.processed_image_url)
        if url  # filter out None / empty
    })

    users = UserRepository(session)
    user = await users.get_or_raise(uid)
    await session.delete(user)
    await session.commit()

    # Queue GCS / disk cleanup as a fire-and-forget background task.
    if image_urls:
        bg.add_task(_cleanup_user_uploads, image_urls, user_id)
        logger.info("upload_cleanup_queued", user_id=user_id, count=len(image_urls))

    logger.info("account_erased", user_id=user_id)


@router.get("/me/export")
@limiter.limit("3/hour")
async def export_my_data(
    request: Request,
    user_id: CurrentUser,
    session: DbSession,
):
    """Return a JSON export of everything held about the authenticated user (GDPR Art. 20)."""
    from datetime import date as _date
    from sqlalchemy import select
    from app.models.closet import ClosetItem
    from app.models.trips import Trip
    from app.models.ai_chat import AIChatSession, AIChatMessage

    uid = _uuid.UUID(user_id)
    users = UserRepository(session)
    user = await users.get_or_raise(uid)

    # Closet items
    closet_rows = (await session.execute(
        select(ClosetItem).where(ClosetItem.user_id == uid)
    )).scalars().all()

    # Trips
    trip_rows = (await session.execute(
        select(Trip).where(Trip.user_id == uid)
    )).scalars().all()

    # AI chat sessions + messages
    session_rows = (await session.execute(
        select(AIChatSession).where(AIChatSession.user_id == uid)
    )).scalars().all()
    session_ids = [s.id for s in session_rows]
    message_rows = []
    if session_ids:
        message_rows = (await session.execute(
            select(AIChatMessage).where(AIChatMessage.session_id.in_(session_ids))
        )).scalars().all()

    def _str(v):
        if isinstance(v, (_uuid.UUID,)):
            return str(v)
        if isinstance(v, _date):
            return v.isoformat()
        return v

    def _row(obj, fields: list[str]) -> dict:
        return {f: _str(getattr(obj, f, None)) for f in fields}

    export = {
        "exported_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "name": user.name,
            "bio": user.bio,
            "avatar_url": user.avatar_url,
            "auth_provider": user.auth_provider,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat(),
            "body_profile": user.body_profile,
            "style_profile": user.style_profile,
            "preferences": user.preferences,
        },
        "closet_items": [
            _row(item, ["id", "name", "category", "color", "fabric", "pattern",
                        "season", "occasion", "tags", "brand", "size", "price",
                        "image_url", "notes", "created_at"])
            for item in closet_rows
        ],
        "trips": [
            _row(trip, ["id", "destination", "start_date", "end_date", "purpose", "notes", "created_at"])
            for trip in trip_rows
        ],
        "ai_chat_sessions": [
            {
                **_row(s, ["id", "title", "created_at"]),
                "messages": [
                    _row(m, ["id", "role", "content", "created_at"])
                    for m in message_rows if m.session_id == s.id
                ],
            }
            for s in session_rows
        ],
    }

    return JSONResponse(
        content=export,
        headers={"Content-Disposition": 'attachment; filename="clozehive_data_export.json"'},
    )


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
                url=_oauth_login_redirect(frontend, error="oauth_redirect_mismatch"),
                status_code=302,
            )
        if error and error != "access_denied":
            return RedirectResponse(
                url=_oauth_login_redirect(frontend, error="oauth_failed", reason=error.lower()),
                status_code=302,
            )
        return RedirectResponse(
            url=_oauth_login_redirect(frontend, error="oauth_cancelled"),
            status_code=302,
        )

    # Validate CSRF state stored in Redis
    stored = await cache_service.get(_OAUTH_STATE_PREFIX + state)
    if not stored:
        logger.warning("google_oauth_invalid_state", state=state[:8])
        return RedirectResponse(
            url=_oauth_login_redirect(frontend, error="oauth_invalid_state"),
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

        auth_result, refresh_raw = await svc.google_oauth_login(google_id, email, name, avatar_url)

        # Store only the access token in Redis under a short-lived one-time code so that
        # JWTs are never exposed in the redirect URL (browser history / Referer / logs).
        # The refresh token is delivered via HttpOnly cookie through /auth/oauth/exchange.
        code = secrets.token_urlsafe(32)
        await cache_service.set(
            _OAUTH_CODE_PREFIX + code,
            {
                "access_token": auth_result.access_token,
                # Stored so /oauth/exchange can set the cookie — not returned to client JS.
                "_refresh_token": refresh_raw,
            },
            ttl=_OAUTH_CODE_TTL,
        )
        return RedirectResponse(
            url=f"{frontend}/oauth/callback?code={code}",
            status_code=302,
        )

    except Exception as exc:
        logger.error(
            "google_oauth_callback_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        reason = "oauth_failed_generic"
        err_lower = str(exc).lower()
        if "redirect_uri_mismatch" in err_lower:
            reason = "redirect_uri_mismatch"
        elif "invalid_client" in err_lower:
            reason = "invalid_client"
        elif "invalid_grant" in err_lower:
            reason = "oauth_code_invalid"
        elif "unauthorized_client" in err_lower:
            reason = "oauth_exchange_unauthorized"
        elif "failed to fetch google user profile" in err_lower:
            reason = "oauth_profile_fetch"
        elif "token" in err_lower:
            reason = "token_exchange"
        elif "timeout" in err_lower or "timed out" in err_lower or "network" in err_lower:
            reason = "oauth_exchange_network"
        # When OAUTH_DEBUG_ERRORS is on, surface the real error type+message to the
        # login page so it can be diagnosed without server log access. Off by default.
        detail = None
        if settings.oauth_debug_errors:
            detail = f"{type(exc).__name__}: {exc}"
        return RedirectResponse(
            url=_oauth_login_redirect(frontend, error="oauth_failed", reason=reason, detail=detail),
            status_code=302,
        )


# ---------------------------------------------------------------------------
# OAuth token exchange — converts the short-lived one-time code issued by
# google_callback into real JWT tokens.  The code is deleted on first read so
# it cannot be replayed.
# ---------------------------------------------------------------------------

class _OAuthExchangeRequest(BaseModel):
    code: str


@router.post("/oauth/exchange", response_model=TokenResponse, tags=["Auth"])
async def oauth_exchange(response: Response, body: _OAuthExchangeRequest):
    """Exchange a one-time OAuth code (from the redirect URL) for JWT tokens.

    The code is valid for 2 minutes and is deleted immediately after use.
    Returns 400 if the code is missing, already used, or expired.

    The refresh token is set as an HttpOnly cookie — it is NOT returned in the
    response body, so JavaScript code can never read it.
    """
    redis_key = _OAUTH_CODE_PREFIX + body.code
    stored = await cache_service.get(redis_key)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth code is invalid or has expired. Please sign in again.",
        )

    # Delete before returning — strictly one-time use even under concurrent requests
    await cache_service.delete(redis_key)

    # Set refresh token as HttpOnly cookie; access token returned in body only.
    refresh_raw = stored.get("_refresh_token") or stored.get("refresh_token", "")
    if refresh_raw:
        _set_refresh_cookie(response, refresh_raw)

    return TokenResponse(
        access_token=stored["access_token"],
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )
