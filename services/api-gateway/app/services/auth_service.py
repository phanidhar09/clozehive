"""
Auth service — signup, login, token refresh, OAuth.
Single source of truth for all authentication logic.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, BadRequestError, ConflictError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import RefreshToken, User, UserCredential
from app.repositories.user_repo import (
    CredentialRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import AuthResponse, SignupRequest, TokenResponse, UserResponse

logger = get_logger("auth_service")
settings = get_settings()


def _build_tokens(user_id: str, role: str) -> tuple[str, str]:
    """Return (access_token, refresh_token_raw)."""
    return create_access_token(user_id, role), create_refresh_token(user_id)


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        name=user.name,
        bio=user.bio,
        avatar_url=user.avatar_url,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.creds = CredentialRepository(session)
        self.tokens = RefreshTokenRepository(session)

    async def signup(self, data: SignupRequest) -> AuthResponse:
        if await self.users.email_exists(data.email):
            raise ConflictError("Email already registered")
        if await self.users.username_exists(data.username):
            raise ConflictError("Username already taken")

        user = await self.users.create(
            email=data.email.lower(),
            username=data.username.lower(),
            name=data.name,
            role="user",
        )

        await self.creds.create(
            user_id=user.id,
            password_hash=hash_password(data.password),
        )

        access, refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, refresh_raw)

        logger.info("user_signed_up", user_id=str(user.id), username=user.username)
        return AuthResponse(
            user=_user_response(user),
            access_token=access,
            refresh_token=refresh_raw,
        )

    async def login(self, identifier: str, password: str) -> AuthResponse:
        # Look up by email or username
        if "@" in identifier:
            user = await self.users.get_by_email(identifier.lower())
        else:
            user = await self.users.get_by_username(identifier.lower())

        if not user or not user.is_active:
            raise AuthenticationError("Invalid credentials")

        cred = await self.creds.get_by_user_id(user.id)
        if not cred or not cred.password_hash:
            raise AuthenticationError("Account uses social login — please sign in with Google")

        if not verify_password(password, cred.password_hash):
            raise AuthenticationError("Invalid credentials")

        access, refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, refresh_raw)

        logger.info("user_logged_in", user_id=str(user.id))
        return AuthResponse(
            user=_user_response(user),
            access_token=access,
            refresh_token=refresh_raw,
        )

    async def refresh(self, raw_token: str) -> TokenResponse:
        token_hash = hash_token(raw_token)
        stored = await self.tokens.get_valid(token_hash)

        if not stored:
            raise AuthenticationError("Invalid or expired refresh token")

        user = await self.users.get(stored.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("Account not found or inactive")

        # Rotate: revoke old token, issue new pair
        await self.tokens.update(stored, revoked=True)
        access, new_refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, new_refresh_raw)

        logger.info("token_refreshed", user_id=str(user.id))
        return TokenResponse(
            access_token=access,
            refresh_token=new_refresh_raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def logout(self, user_id: UUID, raw_token: str) -> None:
        token_hash = hash_token(raw_token)
        stored = await self.tokens.get_valid(token_hash)
        if stored:
            await self.tokens.update(stored, revoked=True)
        logger.info("user_logged_out", user_id=str(user_id))

    async def logout_all(self, user_id: UUID) -> None:
        await self.tokens.revoke_all_for_user(user_id)
        logger.info("all_sessions_revoked", user_id=str(user_id))

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        cred = await self.creds.get_by_user_id(user_id)
        if not cred or not verify_password(current_password, cred.password_hash or ""):
            raise AuthenticationError("Current password is incorrect")
        await self.creds.update(cred, password_hash=hash_password(new_password))
        await self.tokens.revoke_all_for_user(user_id)
        logger.info("password_changed", user_id=str(user_id))

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _store_refresh(self, user_id: UUID, raw_token: str) -> RefreshToken:
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        return await self.tokens.create(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
