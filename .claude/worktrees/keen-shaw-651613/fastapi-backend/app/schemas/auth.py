"""
Authentication request / response schemas.

All request bodies are validated by Pydantic before reaching service layer.
Password rules are documented in the OpenAPI spec via Field descriptions.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Requests ──────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, examples=["Phani Reddy"])
    email: EmailStr
    username: str = Field(
        ..., min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_]+$",
        description="3–40 chars; letters, digits, and underscores only",
    )
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Min 8 chars, at least one uppercase letter and one digit",
    )

    @field_validator("username")
    @classmethod
    def username_lowercase(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email address or username")
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Google Identity Services credential (ID token)")


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Used by POST /auth/change-password (requires current session)."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("New password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("New password must contain at least one digit")
        return v


class LogoutRequest(BaseModel):
    """
    Body for POST /auth/logout.
    The refresh token is used to identify and revoke a specific session.
    If omitted, the endpoint will attempt to revoke the current session
    using the bearer token's JTI.
    """
    refresh_token: Optional[str] = None


# ── Responses ─────────────────────────────────────────────────────────────────

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Tell the client exactly when to refresh so it can schedule proactively.
    expires_in: int = Field(
        description="Access token lifetime in seconds",
        default_factory=lambda: __import__("app.core.config", fromlist=["settings"]).settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


class AuthUserResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    role: str = "user"          # RBAC role embedded in every auth response
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: AuthUserResponse
    tokens: TokenPair


class MessageResponse(BaseModel):
    """Generic success message response."""
    message: str
    detail: Optional[str] = None
