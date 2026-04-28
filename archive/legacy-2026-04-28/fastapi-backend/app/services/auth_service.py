"""
Authentication service — signup, login, token refresh, Google OAuth.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    decode_token,
    TokenError,
)
from app.models.user import User, RefreshToken
from app.schemas.auth import SignupRequest, LoginRequest, TokenPair, AuthUserResponse, AuthResponse

logger = logging.getLogger("clozehive.auth")


def _hash_token(token: str) -> str:
    """Store a SHA-256 hash of the refresh token (never store raw)."""
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:

    # ── Signup ────────────────────────────────────────────────────────────────

    @staticmethod
    async def signup(db: AsyncSession, data: SignupRequest) -> AuthResponse:
        # Check uniqueness
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
        )
        db.add(user)
        await db.flush()  # get the auto-generated id

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        logger.info("New user signed up: %s (id=%d)", user.username, user.id)
        return AuthResponse(
            user=AuthUserResponse.model_validate(user),
            tokens=tokens,
        )

    # ── Login ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> AuthResponse:
        identifier = data.identifier.strip()

        # Try email first, then username
        if "@" in identifier:
            user = await db.scalar(select(User).where(User.email == identifier.lower()))
        else:
            user = await db.scalar(select(User).where(User.username == identifier.lower()))

        if user is None or user.password_hash is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        return AuthResponse(
            user=AuthUserResponse.model_validate(user),
            tokens=tokens,
        )

    # ── Refresh ───────────────────────────────────────────────────────────────

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> TokenPair:
        
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except TokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

        token_hash = _hash_token(refresh_token)
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

        # Check expiry
        if stored.expires_at < datetime.now(tz=timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        # Rotate — revoke old, issue new pair
        stored.revoked = True
        user = await db.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()
        return tokens

    # ── Google OAuth ─────────────────────────────────────────────────────────

    @staticmethod
    async def google_login(db: AsyncSession, id_token: str) -> AuthResponse:
        """
        Verify a Google / Firebase ID token and upsert the user.
        Requires GOOGLE_CLIENT_ID env var and the `google-auth` package.
        Falls back gracefully when not configured.
        """
        try:
            from google.oauth2 import id_token as google_id_token  # type: ignore
            from google.auth.transport import requests as google_requests  # type: ignore

            idinfo = google_id_token.verify_oauth2_token(
                id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Google token: {exc}",
            )

        google_id = idinfo["sub"]
        email = idinfo.get("email", "").lower()
        name = idinfo.get("name", "")
        avatar_url = idinfo.get("picture")

        # Upsert by google_id
        user = await db.scalar(select(User).where(User.google_id == google_id))
        if user is None:
            # Try to merge with existing email account
            user = await db.scalar(select(User).where(User.email == email))

        if user is None:
            # Brand-new user via Google
            base_username = email.split("@")[0].lower()[:38]
            username = base_username
            # Ensure uniqueness
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
            )
            db.add(user)
            await db.flush()
        else:
            user.google_id = google_id
            if avatar_url:
                user.avatar_url = avatar_url

        tokens = await AuthService._issue_tokens(db, user)
        await db.commit()

        return AuthResponse(
            user=AuthUserResponse.model_validate(user),
            tokens=tokens,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
        access = create_access_token(
            subject=user.id,
            extra={"username": user.username, "name": user.name},
        )
        raw_refresh, expires_at = create_refresh_token(subject=user.id)

        db.add(RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(raw_refresh),
            expires_at=expires_at,
        ))

        return TokenPair(access_token=access, refresh_token=raw_refresh)
