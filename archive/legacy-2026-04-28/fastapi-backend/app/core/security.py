"""
Security utilities: password hashing, JWT creation/verification.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ── Password hashing ─────────────────────────────────────────────────────────
# Use bcrypt directly to avoid passlib compatibility issues on Python 3.12+

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── Token creation ───────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(subject: str | int, extra: dict | None = None) -> str:
    """
    Create a short-lived JWT access token.

    :param subject: user id (will be stored as ``sub`` claim)
    :param extra:   additional claims merged into the payload
    """
    expire = _utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(subject),
        "type": "access",
        "exp": expire,
        "iat": _utcnow(),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> tuple[str, datetime]:
    """
    Create a long-lived refresh token.
    Returns (encoded_token, expiry_datetime).
    """
    expire = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict = {
        "sub": str(subject),
        "type": "refresh",
        "exp": expire,
        "iat": _utcnow(),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire


# ── Token verification ───────────────────────────────────────────────────────

class TokenError(Exception):
    """Raised for any JWT validation failure."""


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT.

    :raises TokenError: if invalid, expired, or wrong type
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")

    return payload


def get_user_id_from_token(token: str) -> int:
    """Convenience: decode access token and return integer user id."""
    payload = decode_token(token, expected_type="access")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("Token payload missing valid 'sub'") from exc
