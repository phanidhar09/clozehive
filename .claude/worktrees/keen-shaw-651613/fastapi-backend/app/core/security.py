"""
Security utilities: password hashing, JWT creation/verification, CSRF tokens.

Design decisions:
  - bcrypt rounds=12: ~250 ms on modern hardware — fast enough for UX, slow
    enough to make offline dictionary attacks prohibitively expensive.
  - JWT algorithm explicitly whitelisted: prevents the 'alg: none' attack and
    RS256/HS256 confusion when the same code handles multiple token types.
  - Refresh tokens are stored as SHA-256 hashes in the DB so a DB breach
    cannot directly replay stolen tokens.
  - CSRF uses the Double-Submit Cookie pattern: an opaque HMAC-signed token is
    set in a readable (non-HttpOnly) cookie and must also appear in the
    X-CSRF-Token header. State-mutating requests (POST/PUT/PATCH/DELETE) are
    rejected if the two values don't match.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ── Allowed algorithms whitelist ─────────────────────────────────────────────
# Only ever accept the algorithm we configured. This prevents the 'alg:none'
# attack and RS256/HS256 confusion bugs.
_ALLOWED_ALGORITHMS = {settings.JWT_ALGORITHM}


# ── Password hashing ─────────────────────────────────────────────────────────
# Use bcrypt directly to avoid passlib compatibility issues on Python 3.12+.

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* using 12 rounds (≈250 ms)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt comparison. Returns False on any error."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(subject: str | int, role: str = "user", extra: dict | None = None) -> str:
    """
    Create a short-lived JWT access token.

    Claims:
      sub   — user id (string)
      type  — 'access' (prevents refresh tokens being used as access tokens)
      role  — RBAC role embedded in the token (avoids a DB lookup per request)
      exp   — expiry (ACCESS_TOKEN_EXPIRE_MINUTES from now)
      iat   — issued-at
      jti   — unique token id (allows future per-token revocation)
    """
    expire = _utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(subject),
        "type": "access",
        "role": role,
        "exp": expire,
        "iat": _utcnow(),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        # Caller may add e.g. username/name for convenience, but these are
        # non-authoritative — always re-fetch from DB for sensitive decisions.
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> tuple[str, datetime]:
    """
    Create a long-lived refresh token.
    Returns (raw_token, expiry_datetime).
    Store only the SHA-256 hash in the DB.
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


def hash_token(token: str) -> str:
    """SHA-256 hash of a raw token string. Use to store refresh tokens safely."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Token verification ────────────────────────────────────────────────────────

class TokenError(Exception):
    """Raised for any JWT validation failure (expired, invalid, wrong type, etc.)."""


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT.

    Security:
      - Only algorithms in _ALLOWED_ALGORITHMS are accepted (no 'alg:none').
      - Token type claim is verified to prevent access/refresh token confusion.

    :raises TokenError: if invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=list(_ALLOWED_ALGORITHMS),  # explicit whitelist
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise TokenError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )

    return payload


def get_user_id_from_token(token: str) -> int:
    """Convenience: decode access token and return integer user id."""
    payload = decode_token(token, expected_type="access")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("Token payload missing valid 'sub'") from exc


# ── CSRF — Double-Submit Cookie pattern ───────────────────────────────────────
#
# How it works:
#   1. On first authenticated request (or login), we set a readable cookie
#      named `csrftoken` containing an HMAC-signed opaque token.
#   2. For every state-mutating request (POST/PUT/PATCH/DELETE), the client
#      JS must read that cookie and echo it back in the X-CSRF-Token header.
#   3. The server validates the header value against the cookie.
#
# Why this is safe:
#   Cross-site requests cannot read cookies from another origin (SameSite=Lax
#   also helps), so an attacker cannot forge the header value.
#
# Note: since most API calls already use `Authorization: Bearer <token>` (which
# browsers cannot auto-attach cross-origin), CSRF risk is low — but the pattern
# is implemented here for cookie-based flows and defense-in-depth.

def generate_csrf_token() -> str:
    """
    Generate a new CSRF token: a URL-safe random string signed with HMAC-SHA256.
    The token format is:  <random_hex>.<hmac_hex>
    """
    raw = secrets.token_hex(32)
    sig = _csrf_sign(raw)
    return f"{raw}.{sig}"


def validate_csrf_token(token: str) -> bool:
    """
    Verify a CSRF token produced by :func:`generate_csrf_token`.
    Uses `hmac.compare_digest` for constant-time comparison.
    """
    try:
        raw, sig = token.split(".", 1)
    except ValueError:
        return False
    expected = _csrf_sign(raw)
    return hmac.compare_digest(expected, sig)


def _csrf_sign(raw: str) -> str:
    return hmac.new(
        settings.effective_csrf_secret.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()
