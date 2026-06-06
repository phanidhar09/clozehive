"""
Auth service — signup, login, token refresh, OAuth.
Single source of truth for all authentication logic.
"""

from __future__ import annotations

from typing import Optional

import secrets
from datetime import timezone, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, BadRequestError, ConflictError
from app.core.logging import get_logger
from app.core.redis import (
    get_state_redis,
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import RefreshToken, User, UserCredential
from app.api.v1.identity.repositories.user_repo import (
    CredentialRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.api.v1.identity.schemas.auth import AuthResponse, SignupRequest, UserResponse
from app.api.v1.identity.services.style_profile_service import create_default_profile_row
from app.utils.username import generate_unique_username

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
        auth_provider=user.auth_provider,
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.creds = CredentialRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.reset_tokens = PasswordResetTokenRepository(session)

    async def signup(self, data: SignupRequest) -> tuple[AuthResponse, str]:
        if await self.users.email_exists(data.email):
            raise ConflictError("Email already registered")

        # Resolve username: use provided value or auto-generate from name / email
        if data.username:
            if await self.users.username_exists(data.username):
                raise ConflictError("Username already taken")
            resolved_username = data.username.lower()
        else:
            resolved_username = await generate_unique_username(
                self.session, data.name, data.email
            )

        user = await self.users.create(
            email=data.email.lower(),
            username=resolved_username,
            name=data.name,
            role="user",
            auth_provider="local",
        )

        await self.creds.create(
            user_id=user.id,
            password_hash=hash_password(data.password),
        )

        await create_default_profile_row(self.session, user.id)

        access, refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, refresh_raw)

        logger.info("user_signed_up", user_id=str(user.id), username=user.username)
        return AuthResponse(
            user=_user_response(user),
            access_token=access,
        ), refresh_raw

    async def login(self, identifier: str, password: str) -> tuple[AuthResponse, str]:
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

        # Ensure a style-profile row exists (idempotent — skips if already present)
        await create_default_profile_row(self.session, user.id)

        access, refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, refresh_raw)

        logger.info("user_logged_in", user_id=str(user.id))
        return AuthResponse(
            user=_user_response(user),
            access_token=access,
        ), refresh_raw

    async def refresh(self, raw_token: str) -> tuple[str, str]:
        redis = await get_state_redis()
        if not await is_refresh_token_valid(redis, raw_token):
            raise AuthenticationError("Refresh token has been revoked. Please log in again.")

        token_hash = hash_token(raw_token)
        stored = await self.tokens.get_valid(token_hash)

        if not stored:
            raise AuthenticationError("Invalid or expired refresh token")

        user = await self.users.get(stored.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("Account not found or inactive")

        # Rotate with create-before-destroy ordering so a partial failure never
        # locks the user out. The DB revoke + create commit together in this
        # request's transaction; issuing the new token first means that if the
        # request aborts before the old token is revoked, the old token still
        # works and the client simply retries — far safer than revoking first
        # and crashing before the replacement exists.
        access, new_refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, new_refresh_raw)
        await self.tokens.update(stored, revoked=True)
        await revoke_refresh_token(redis, raw_token)

        logger.info("token_refreshed", user_id=str(user.id))
        # Return (new_access_token, new_refresh_raw) so the route can set the cookie.
        return access, new_refresh_raw

    async def logout(self, user_id: UUID, raw_token: str) -> None:
        await self.logout_by_refresh(raw_token)
        logger.info("user_logged_out", user_id=str(user_id))

    async def logout_by_refresh(self, raw_token: str) -> None:
        redis = await get_state_redis()
        await revoke_refresh_token(redis, raw_token)
        token_hash = hash_token(raw_token)
        stored = await self.tokens.get_valid(token_hash)
        if stored:
            await self.tokens.update(stored, revoked=True)
        logger.info("refresh_token_revoked")

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

    async def google_oauth_login(
        self,
        google_id: str,
        email: str,
        name: str,
        avatar_url: Optional[str] = None,
        email_verified: bool = False,
    ) -> tuple[AuthResponse, str]:
        """Find or create a user from Google OAuth, then return a token pair."""
        user = await self.users.get_by_google_id(google_id)

        if not user:
            # Try linking to an existing account by email
            user = await self.users.get_by_email(email.lower())
            if user:
                # SECURITY: only link a Google identity to a pre-existing account
                # when Google asserts the email is verified. Otherwise an attacker
                # who creates a Google account with the victim's email could take
                # over the victim's account on first OAuth login.
                if not email_verified:
                    raise AuthenticationError(
                        "This email is already registered. Sign in with your "
                        "password, or verify your email with Google first."
                    )
                # Link existing account to Google — repair any missing fields
                updates: dict = {"google_id": google_id, "auth_provider": "google"}

                # Repair missing / empty name from Google data
                if not user.name and name:
                    updates["name"] = name

                # Repair missing / empty username — must never be blank
                if not user.username:
                    updates["username"] = await generate_unique_username(
                        self.session, name or user.name, email
                    )

                # Set avatar only when the user has none
                if avatar_url and not user.avatar_url:
                    updates["avatar_url"] = avatar_url

                await self.users.update(user, **updates)
                # Reload so the returned object reflects repaired fields
                await self.session.refresh(user)
            else:
                # Brand-new user via Google
                username = await generate_unique_username(self.session, name, email)
                user = await self.users.create(
                    email=email.lower(),
                    username=username,
                    name=name or email.split("@")[0],
                    google_id=google_id,
                    avatar_url=avatar_url,
                    role="user",
                    is_verified=True,
                    auth_provider="google",
                )
                # No password — OAuth-only account
                await self.creds.create(user_id=user.id, password_hash=None)

        # Ensure a style-profile row exists for every user (idempotent — skips if already present)
        await create_default_profile_row(self.session, user.id)

        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        access, refresh_raw = _build_tokens(str(user.id), user.role)
        await self._store_refresh(user.id, refresh_raw)

        logger.info("google_oauth_login", user_id=str(user.id))
        return AuthResponse(
            user=_user_response(user),
            access_token=access,
        ), refresh_raw

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _store_refresh(self, user_id: UUID, raw_token: str) -> RefreshToken:
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        stored = await self.tokens.create(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        redis = await get_state_redis()
        await store_refresh_token(
            redis,
            str(user_id),
            raw_token,
            settings.refresh_token_expire_days * 24 * 60 * 60,
        )
        return stored

    # ── Password reset ────────────────────────────────────────────────────────

    _RESET_TOKEN_EXPIRE_MINUTES = 30  # short window to reduce brute-force surface

    async def request_password_reset(self, email: str) -> Optional[str]:
        """Generate a reset token for *email* (if it exists).

        Returns the raw token so the caller can send it by email.
        Returns ``None`` when the email is not found — the *caller* must NOT
        reveal this to the client (return a generic success response regardless).

        Security:
        - Only the SHA-256 hash is stored in the DB.
        - Any existing unused tokens for the user are invalidated first.
        - Token expires in 30 minutes.
        """
        user = await self.users.get_by_email(email.lower())
        if not user:
            # Do not reveal that the email does not exist.
            return None

        # Invalidate any existing unused reset tokens to prevent token accumulation.
        await self.reset_tokens.invalidate_all_for_user(user.id)

        raw_token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._RESET_TOKEN_EXPIRE_MINUTES)
        await self.reset_tokens.create(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
        )
        logger.info("password_reset_requested", user_id=str(user.id))
        return raw_token

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Consume *raw_token* and set *new_password*.

        Raises ``AuthenticationError`` if the token is invalid, expired, or
        already used.  Revokes all existing refresh tokens on success so every
        device is signed out.
        """
        token_hash = hash_token(raw_token)
        stored = await self.reset_tokens.get_valid(token_hash)
        if not stored:
            raise AuthenticationError("Invalid or expired password reset link. Please request a new one.")

        user = await self.users.get(stored.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("Account not found or inactive.")

        # Mark token as used — prevents replay even within expiry window.
        await self.reset_tokens.update(stored, used_at=datetime.now(timezone.utc))

        # Update password.
        cred = await self.creds.get_by_user_id(user.id)
        if cred:
            await self.creds.update(cred, password_hash=hash_password(new_password))
        else:
            await self.creds.create(user_id=user.id, password_hash=hash_password(new_password))

        # Revoke all sessions — the user will need to log in again with the new password.
        await self.tokens.revoke_all_for_user(user.id)
        logger.info("password_reset_completed", user_id=str(user.id))
