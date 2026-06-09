"""Tests for JWT access-token decoding."""

from __future__ import annotations

import pytest
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.security import decode_access_token

settings = get_settings()


def _make_token(token_type: str = "access", secret: str | None = None) -> str:
    return jwt.encode(
        {"sub": "user-123", "type": token_type},
        secret or settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def test_valid_access_token_decodes():
    payload = decode_access_token(_make_token())
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_rejected():
    with pytest.raises(JWTError):
        decode_access_token(_make_token(token_type="refresh"))


def test_missing_type_rejected():
    token = jwt.encode({"sub": "user-123"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_wrong_secret_rejected():
    with pytest.raises(JWTError):
        decode_access_token(_make_token(secret="a-completely-different-secret-key-here"))


def test_garbage_token_rejected():
    with pytest.raises(JWTError):
        decode_access_token("not.a.jwt")
