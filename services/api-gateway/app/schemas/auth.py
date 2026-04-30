"""Auth request/response schemas."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email address or username")
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expiry


# ── Personalization sub-schemas ──────────────────────────────────────────────

BodyType = Literal["slim", "athletic", "average", "broad", "curvy", "plus"]
PreferredFit = Literal["slim", "regular", "oversized"]
StyleTag = Literal[
    "casual", "formal", "streetwear", "sporty", "minimal",
    "business", "boho", "vintage", "preppy", "elegant",
]


class BodyProfile(BaseModel):
    height_cm: float | None = Field(None, ge=80, le=260)
    weight_kg: float | None = Field(None, ge=25, le=300)
    body_type: BodyType | None = None
    preferred_fit: PreferredFit | None = None
    shirt_size: str | None = Field(None, max_length=20)
    pant_size: str | None = Field(None, max_length=20)
    shoe_size: str | None = Field(None, max_length=20)


class StyleProfile(BaseModel):
    selected_styles: list[StyleTag] = Field(default_factory=list, max_length=8)
    learned_style: str | None = Field(None, max_length=50)
    learned_at: str | None = None  # ISO timestamp from frontend
    favorite_colors: list[str] = Field(default_factory=list, max_length=12)
    avoid_colors: list[str] = Field(default_factory=list, max_length=12)


class UserPreferences(BaseModel):
    occasion_focus: list[str] = Field(default_factory=list, max_length=10)
    avoid_categories: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(None, max_length=500)


class UserPermissions(BaseModel):
    location: bool = False
    calendar: bool = False
    location_coords: dict[str, float] | None = None  # { lat, lon }
    location_label: str | None = Field(None, max_length=120)
    timezone: str | None = Field(None, max_length=80)


class AvatarConfig(BaseModel):
    skin_tone: str | None = Field(None, max_length=20)
    hair_color: str | None = Field(None, max_length=20)
    hair_style: str | None = Field(None, max_length=20)
    body_type: str | None = Field(None, max_length=20)
    outfit: str | None = Field(None, max_length=20)


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    name: str
    bio: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    is_verified: bool
    body_profile: dict[str, Any] | None = None
    style_profile: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    permissions: dict[str, Any] | None = None
    avatar_config: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = None
    # Personalization sections — clients send only the keys they want to update.
    body_profile: BodyProfile | None = None
    style_profile: StyleProfile | None = None
    preferences: UserPreferences | None = None
    permissions: UserPermissions | None = None
    avatar_config: AvatarConfig | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v
