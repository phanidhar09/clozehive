"""
Authentication request/response schemas.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Requests ─────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, examples=["Phani Reddy"])
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)

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
    identifier: str = Field(..., description="Email or username")
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Firebase / Google ID token")


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Responses ────────────────────────────────────────────────────────────────

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthUserResponse(BaseModel):
    id: int
    name: str
    username: str
    email: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: AuthUserResponse
    tokens: TokenPair
