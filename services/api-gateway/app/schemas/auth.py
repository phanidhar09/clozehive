"""Auth request/response schemas."""

from __future__ import annotations

import re
from typing import Optional, Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator

from app.schemas.validators import strip_string


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    email: EmailStr = Field(..., max_length=254)
    # username is optional — the service auto-generates one from name/email if omitted
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    # GDPR Art. 6/7 — explicit consent is required before account creation
    gdpr_consent: bool = Field(..., description="User must explicitly accept the Privacy Policy and Terms of Service")

    @field_validator("gdpr_consent")
    @classmethod
    def consent_must_be_given(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the Privacy Policy and Terms of Service to create an account")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return strip_string(v)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return strip_string(v).lower()

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must be 8-128 characters and contain at least one letter and one number")
        return v


UserRegister = SignupRequest


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email address or username")
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    # Kept for backwards compatibility; the cookie path is preferred.
    refresh_token: Optional[str] = None


# ── Personalization sub-schemas ──────────────────────────────────────────────

BodyType = Literal["slim", "athletic", "average", "broad", "curvy", "plus"]
PreferredFit = Literal["slim", "regular", "oversized"]
StyleTag = Literal[
    "casual", "formal", "streetwear", "sporty", "minimal",
    "business", "boho", "vintage", "preppy", "elegant",
]


class BodyProfile(BaseModel):
    height_cm: Optional[float] = Field(None, ge=80, le=260)
    weight_kg: Optional[float] = Field(None, ge=25, le=300)
    body_type: Optional[BodyType] = None
    preferred_fit: Optional[PreferredFit] = None
    shirt_size: Optional[str] = Field(None, max_length=20)
    pant_size: Optional[str] = Field(None, max_length=20)
    shoe_size: Optional[str] = Field(None, max_length=20)


class StyleProfile(BaseModel):
    selected_styles: list[StyleTag] = Field(default_factory=list, max_length=8)
    learned_style: Optional[str] = Field(None, max_length=50)
    learned_at: Optional[str] = None  # ISO timestamp from frontend
    favorite_colors: list[str] = Field(default_factory=list, max_length=12)
    avoid_colors: list[str] = Field(default_factory=list, max_length=12)


class UserPreferences(BaseModel):
    occasion_focus: list[str] = Field(default_factory=list, max_length=10)
    avoid_categories: list[str] = Field(default_factory=list, max_length=20)
    notes: Optional[str] = Field(None, max_length=500)


class UserPermissions(BaseModel):
    location: bool = False
    calendar: bool = False
    location_coords: Optional[dict[str, float]] = None  # { lat, lon }
    location_label: Optional[str] = Field(None, max_length=120)
    timezone: Optional[str] = Field(None, max_length=80)


class AvatarConfig(BaseModel):
    skin_tone: Optional[str] = Field(None, max_length=20)
    hair_color: Optional[str] = Field(None, max_length=20)
    hair_style: Optional[str] = Field(None, max_length=20)
    body_type: Optional[str] = Field(None, max_length=20)
    outfit: Optional[str] = Field(None, max_length=20)


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    name: str
    bio: Optional[str]
    avatar_url: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    auth_provider: str = "local"
    body_profile: Optional[dict[str, Any]] = None
    style_profile: Optional[dict[str, Any]] = None
    preferences: Optional[dict[str, Any]] = None
    permissions: Optional[dict[str, Any]] = None
    avatar_config: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_name(self) -> str:
        """Alias for name — lets the frontend use a consistent field name."""
        return self.name or self.username


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    # refresh_token is intentionally NOT returned in the response body — it is
    # set as an HttpOnly cookie by the route handler so JavaScript cannot read it.
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    # refresh_token omitted from body — delivered via HttpOnly cookie.
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expiry


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=60)
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    # Personalization sections — clients send only the keys they want to update.
    body_profile: Optional[BodyProfile] = None
    style_profile: Optional[StyleProfile] = None
    preferences: Optional[UserPreferences] = None
    permissions: Optional[UserPermissions] = None
    avatar_config: Optional[AvatarConfig] = None

    @field_validator("name", "bio", mode="before")
    @classmethod
    def strip_profile_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return v.lower()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must be 8-128 characters and contain at least one letter and one number")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return strip_string(v).lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must be 8-128 characters and contain at least one letter and one number")
        return v
