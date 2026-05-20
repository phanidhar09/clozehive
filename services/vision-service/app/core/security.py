"""
Security utilities — JWT token decoding for vision-service.
"""

from __future__ import annotations

from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

ACCESS_TOKEN_TYPE = "access"


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an access JWT.
    Raises jose.JWTError on any failure — caller must handle it.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise JWTError("Wrong token type")
    return payload
