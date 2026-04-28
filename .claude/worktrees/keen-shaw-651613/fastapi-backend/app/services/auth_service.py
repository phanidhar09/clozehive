"""
Authentication service — signup, login, token refresh, logout, Google OAuth.

Security decisions:
  Account lockout:  After MAX_LOGIN_ATTEMPTS consecutive failures the account is
                    locked for LOCKOUT_DURATION_MINUTES. The lock is stored in the
                    DB (locked_until column) so it survives server restarts and
                    works across multiple API instances.

  Error messages:   Login always returns "Invalid credentials" regardless of
                    whether the identifier or password was wrong. This prevents
                    user-enumeration attacks.

  Token rotation:   Every /refresh call revokes the presented refresh token and
                    issues a brand-new pair. Compromised refresh tokens therefore
                    have a short window of abuse.

  Google OAuth:     We validate the audience claim (aud == GOOGLE_CLIENT_ID) so
                    tokens issued to a different Google app cannot be replayed here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User, RefreshToken, UserRole
from app.schemas.auth import (
    AuthResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    TokenPair,
)

logger = logging.getLogger("clozehive.auth")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class AuthService:

    # ── Signup ────────────────────────────────────────────────────────────────

    @staticmethod
    async def signup(db: AsyncSession, data: SignupRequest) -> AuthResponse:
        """Create a new account and return tokens immediately (no email verify step)."""
        existing_email = await db.scalar(select(User).where(User.email == data.email.lower()))
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        existing_username = await db.scalar(select(User).where(User.username == data.username.lower()))
        if existing_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

        user = User(
            name=data.name,
            email=data.email.lower(),
            username=data.username.lower(),
            password_hash=hash_password(data.password),
            role=UserRole.USER,
        )
        db.add(user)
        await db.flush()  # get auto-generated id before issuing tokens

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        logger.info("signup  user=%s id=%d", user.username, user.id)
        return AuthResponse(user=AuthUserResponse.model_validate(user), tokens=tokens)

    # ── Login ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> AuthResponse:
        """
        Authenticate with email/username + password.

        Security: always returns the same generic error for wrong identifier
        or wrong password to prevent user enumeration.
        """
        identifier = data.identifier.strip()

        # Resolve user by email or username
        if "@" in identifier:
            user = await db.scalar(select(User).where(User.email == identifier.lower()))
        else:
            user = await db.scalar(select(User).where(User.username == identifier.lower()))

        # --- Validate account exists and has a password (not Google-only) ---
        if user is None or user.password_hash is None:
            # Constant-time delay to prevent timing-based user enumeration
            verify_password("dummy", "$2b$12$" + "x" * 53)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # --- Account lockout check ---
        if user.locked_until and user.locked_until > _utcnow():
            remaining = int((user.locked_until - _utcnow()).total_seconds() // 60) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked due to too many failed attempts. Try again in {remaining} minute(s).",
            )

        # --- Password verification ---
        if not verify_password(data.password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = _utcnow() + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
                logger.warning(
                    "login_locked  user=%s id=%d attempts=%d",
                    user.username, user.id, user.failed_login_attempts,
                )
            else:
                logger.warning(
                    "login_failed  user=%s id=%d attempt=%d/%d",
                    user.username, user.id,
                    user.failed_login_attempts, settings.MAX_LOGIN_ATTEMPTS,
                )
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # --- Deactivated account ---
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

        # --- Success: reset lockout counters and record login ---
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = _utcnow()

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        logger.info("login_ok  user=%s id=%d", user.username, user.id)
        return AuthResponse(user=AuthUserResponse.model_validate(user), tokens=tokens)

    # ── Token Refresh ─────────────────────────────────────────────────────────

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> TokenPair:
        """
        Rotate a refresh token.
        The presented token is immediately revoked; a new pair is issued.
        """
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except TokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

        token_hash = hash_token(refresh_token)
        stored = await db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked == False,  # noqa: E712
            )
        )
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or has been revoked",
            )

        if stored.expires_at < _utcnow():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        # Revoke old token before issuing a new pair (rotation)
        stored.revoked = True

        user = await db.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found or deactivated")

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()
        return tokens

    # ── Logout (single session) ───────────────────────────────────────────────

    @staticmethod
    async def logout(db: AsyncSession, user_id: int, refresh_token: Optional[str]) -> MessageResponse:
        """
        Revoke the current session's refresh token.

        If *refresh_token* is provided we look up the exact token record.
        Otherwise we revoke the most-recently-issued non-revoked token for
        this user (best-effort; client should always send the refresh token).
        """
        if refresh_token:
            token_hash = hash_token(refresh_token)
            stored = await db.scalar(
                select(RefreshToken).where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked == False,  # noqa: E712
                )
            )
            if stored:
                stored.revoked = True
        else:
            # Revoke the latest active session for this user
            stored = await db.scalar(
                select(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
                .order_by(RefreshToken.created_at.desc())
            )
            if stored:
                stored.revoked = True

        await db.commit()
        logger.info("logout  user_id=%d", user_id)
        return MessageResponse(message="Logged out successfully")

    # ── Logout from all devices ───────────────────────────────────────────────

    @staticmethod
    async def logout_all(db: AsyncSession, user_id: int) -> MessageResponse:
        """
        Revoke every active refresh token for this user.
        All other browser/device sessions will fail on next token refresh.
        """
        await db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == False,  # noqa: E712
            )
        )
        await db.commit()
        logger.info("logout_all  user_id=%d", user_id)
        return MessageResponse(message="Logged out from all devices")

    # ── Change password ───────────────────────────────────────────────────────

    @staticmethod
    async def change_password(
        db: AsyncSession, user_id: int, data: ChangePasswordRequest
    ) -> MessageResponse:
        """
        Verify the current password, set the new one, and revoke all
        existing refresh tokens (forces re-login on all other devices).
        """
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not user.password_hash or not verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

        if data.current_password == data.new_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must differ from current password",
            )

        user.password_hash = hash_password(data.new_password)

        # Security: revoke all sessions — an attacker who obtained the old
        # password-based session should not retain access.
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        await db.commit()

        logger.info("password_changed  user_id=%d", user_id)
        return MessageResponse(
            message="Password changed successfully",
            detail="All active sessions have been revoked. Please log in again.",
        )

    # ── Google OAuth ─────────────────────────────────────────────────────────

    @staticmethod
    async def google_login(db: AsyncSession, id_token: str) -> AuthResponse:
        """
        Verify a Google Identity Services ID token and upsert the user.

        Security:
          - Verifies the token signature and expiry (done by google-auth library).
          - Validates the `aud` (audience) claim equals our GOOGLE_CLIENT_ID so
            tokens issued to other Google apps cannot be replayed here.
          - Falls back with a clear error when GOOGLE_CLIENT_ID is not configured.
        """
        if not settings.GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Google OAuth is not configured on this server",
            )

        try:
            from google.oauth2 import id_token as google_id_token  # type: ignore
            from google.auth.transport import requests as google_requests  # type: ignore

            idinfo = google_id_token.verify_oauth2_token(
                id_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,  # audience validation happens here
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Google token: {exc}",
            )

        # Extra audience check (defense in depth; library should already enforce this)
        if idinfo.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token audience mismatch",
            )

        google_id = idinfo["sub"]
        email = idinfo.get("email", "").lower()
        name = idinfo.get("name", "") or email.split("@")[0]
        avatar_url = idinfo.get("picture")

        # Upsert: find by google_id first, then fall back to email merge
        user = await db.scalar(select(User).where(User.google_id == google_id))
        if user is None:
            user = await db.scalar(select(User).where(User.email == email))

        if user is None:
            # New user via Google — generate a unique username from their email
            base_username = email.split("@")[0].lower()[:38]
            username = base_username
            suffix = 0
            while await db.scalar(select(User).where(User.username == username)):
                suffix += 1
                username = f"{base_username}{suffix}"

            user = User(
                name=name,
                email=email,
                username=username,
                google_id=google_id,
                avatar_url=avatar_url,
                role=UserRole.USER,
            )
            db.add(user)
            await db.flush()
        else:
            # Update Google-sourced fields for returning users
            user.google_id = google_id
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url

        user.last_login = _utcnow()
        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        logger.info("google_login  user=%s id=%d", user.username, user.id)
        return AuthResponse(user=AuthUserResponse.model_validate(user), tokens=tokens)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
        """
        Issue a new access + refresh token pair for *user*.
        The refresh token hash is persisted to the DB.
        """
        access = create_access_token(
            subject=user.id,
            role=user.role.value if user.role else "user",
            extra={"username": user.username, "name": user.name},
        )
        raw_refresh, expires_at = create_refresh_token(subject=user.id)

        db.add(RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
        ))

        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
