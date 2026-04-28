"""
Security utilities — JWT tokens, password hashing, OAuth helpers.
All crypto operations in one place, never scattered across the app.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

# ── Token types ───────────────────────────────────────────────────────────────

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt (cost=12)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time compare — returns False on any error, never raises."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT tokens ────────────────────────────────────────────────────────────────

def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str = "user") -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return _encode(payload)


def create_refresh_token(user_id: str) -> str:
    """Returns a cryptographically secure random token (not JWT) for refresh."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an access JWT.
    Raises jose.JWTError on any failure — caller must handle it.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise JWTError("Wrong token type")
    return payload


def hash_token(raw_token: str) -> str:
    """SHA-256 hash a refresh token for safe storage in the database."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ── OAuth ─────────────────────────────────────────────────────────────────────

def build_google_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
