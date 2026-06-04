"""Pydantic models for /profile/style* endpoints."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

GenderValue = Literal["male", "female", "non_binary", "prefer_not_to_say", "custom"]
HeightUnit = Literal["cm", "ft_in"]
WeightUnit = Literal["kg", "lb"]
UndertoneValue = Literal["warm", "cool", "neutral"]

_TAG_RE = re.compile(r"<[^>]*>")

MAX_LIST_LEN = 64
MAX_STR_ITEM = 120


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s).strip()


def _sanitize_str(v: str | None, max_len: int) -> str | None:
    if v is None:
        return None
    t = _strip_tags(v)
    return t[:max_len] if t else None


def _sanitize_str_list(v: list[Any] | None, max_items: int = MAX_LIST_LEN) -> list[str]:
    if not v:
        return []
    out: list[str] = []
    for x in v[:max_items]:
        if x is None:
            continue
        s = _strip_tags(str(x).strip())
        if s:
            out.append(s[:MAX_STR_ITEM])
    return out


def _sanitize_size_profile(v: dict[str, Any] | None) -> dict[str, str]:
    if not v:
        return {}
    out: dict[str, str] = {}
    for k, val in list(v.items())[:80]:
        key = _strip_tags(str(k).strip())[:80]
        if not key:
            continue
        sv = _strip_tags(str(val).strip())[:200]
        if sv:
            out[key] = sv
    return out


class StyleProfileCreate(BaseModel):
    gender: GenderValue | None = None
    custom_gender: str | None = Field(None, max_length=120)
    height_value: Annotated[Decimal | None, Field(None)]
    height_unit: HeightUnit | None = None
    weight_value: Annotated[Decimal | None, Field(None)]
    weight_unit: WeightUnit | None = None
    age_range: str | None = Field(None, max_length=40)
    skin_tone: str | None = Field(None, max_length=32)
    undertone: UndertoneValue | None = None
    body_types: list[str] = Field(default_factory=list)
    custom_body_type: str | None = Field(None, max_length=200)
    fit_preferences: list[str] = Field(default_factory=list)
    custom_fit_notes: str | None = Field(None, max_length=500)
    size_profile: dict[str, str] = Field(default_factory=dict)
    custom_size_notes: str | None = Field(None, max_length=500)
    style_preferences: list[str] = Field(default_factory=list)
    favorite_colors: list[str] = Field(default_factory=list)
    avoided_colors: list[str] = Field(default_factory=list)
    neutral_color_preference: bool | None = None
    bold_color_preference: bool | None = None
    occasion_preferences: list[str] = Field(default_factory=list)
    climate_preferences: list[str] = Field(default_factory=list)

    @field_validator("skin_tone", mode="before")
    @classmethod
    def v_skin_tone(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 32)

    @field_validator("custom_gender", mode="before")
    @classmethod
    def v_custom_gender(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 120)

    @field_validator("custom_body_type", mode="before")
    @classmethod
    def v_custom_body_type(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 200)

    @field_validator("custom_fit_notes", "custom_size_notes", mode="before")
    @classmethod
    def v_notes_fields(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 500)

    @field_validator("age_range", mode="before")
    @classmethod
    def v_age(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = _sanitize_str(str(v), 40)
        return s

    @field_validator(
        "body_types",
        "fit_preferences",
        "style_preferences",
        "favorite_colors",
        "avoided_colors",
        "occasion_preferences",
        "climate_preferences",
        mode="before",
    )
    @classmethod
    def v_lists(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("expected a list")
        return _sanitize_str_list(v)

    @field_validator("size_profile", mode="before")
    @classmethod
    def v_size(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("size_profile must be an object")
        return _sanitize_size_profile(v)

    @model_validator(mode="after")
    def height_pair(self) -> StyleProfileCreate:
        if (self.height_value is not None) ^ (self.height_unit is not None):
            raise ValueError("height_value and height_unit must be set together")
        return self

    @model_validator(mode="after")
    def weight_pair(self) -> StyleProfileCreate:
        if (self.weight_value is not None) ^ (self.weight_unit is not None):
            raise ValueError("weight_value and weight_unit must be set together")
        return self


class StyleProfileUpdate(BaseModel):
    gender: GenderValue | None = None
    custom_gender: str | None = Field(None, max_length=120)
    height_value: Annotated[Decimal | None, Field(None)]
    height_unit: HeightUnit | None = None
    weight_value: Annotated[Decimal | None, Field(None)]
    weight_unit: WeightUnit | None = None
    age_range: str | None = Field(None, max_length=40)
    skin_tone: str | None = Field(None, max_length=32)
    undertone: UndertoneValue | None = None
    body_types: list[str] | None = None
    custom_body_type: str | None = Field(None, max_length=200)
    fit_preferences: list[str] | None = None
    custom_fit_notes: str | None = Field(None, max_length=500)
    size_profile: dict[str, str] | None = None
    custom_size_notes: str | None = Field(None, max_length=500)
    style_preferences: list[str] | None = None
    favorite_colors: list[str] | None = None
    avoided_colors: list[str] | None = None
    neutral_color_preference: bool | None = None
    bold_color_preference: bool | None = None
    occasion_preferences: list[str] | None = None
    climate_preferences: list[str] | None = None
    # v2 onboarding fields
    styling_goals: list[str] | None = None
    avoidances: list[str] | None = None
    pattern_preferences: list[str] | None = None

    @field_validator("custom_gender", "custom_body_type", "custom_fit_notes", "custom_size_notes", mode="before")
    @classmethod
    def v_text_u(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 500)

    @field_validator("skin_tone", mode="before")
    @classmethod
    def v_skin_tone_u(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 32)

    @field_validator("age_range", mode="before")
    @classmethod
    def v_age_u(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return _sanitize_str(str(v), 40)

    @field_validator(
        "body_types",
        "fit_preferences",
        "style_preferences",
        "favorite_colors",
        "avoided_colors",
        "occasion_preferences",
        "climate_preferences",
        "styling_goals",
        "avoidances",
        "pattern_preferences",
        mode="before",
    )
    @classmethod
    def v_lists_u(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("expected a list")
        return _sanitize_str_list(v)

    @field_validator("size_profile", mode="before")
    @classmethod
    def v_size_u(cls, v: Any) -> dict[str, str] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("size_profile must be an object")
        return _sanitize_size_profile(v)


class StyleProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    gender: str | None
    custom_gender: str | None
    height_value: float | None
    height_unit: str | None
    weight_value: float | None
    weight_unit: str | None
    age_range: str | None
    skin_tone: str | None = None
    undertone: str | None = None
    body_types: list[str]
    custom_body_type: str | None
    fit_preferences: list[str]
    custom_fit_notes: str | None
    size_profile: dict[str, str]
    custom_size_notes: str | None
    style_preferences: list[str]
    favorite_colors: list[str]
    avoided_colors: list[str]
    neutral_color_preference: bool | None
    bold_color_preference: bool | None
    occasion_preferences: list[str]
    climate_preferences: list[str]
    onboarding_completed: bool
    onboarding_skipped: bool
    style_summary: str | None = None
    # v2 fields
    styling_goals: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    pattern_preferences: list[str] = Field(default_factory=list)
    style_archetype: str | None = None
    recommendation_rules: dict | None = None
    ai_stylist_context: str | None = None
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_row(cls, row: Any) -> StyleProfileResponse:
        return cls(
            id=row.id,
            user_id=row.user_id,
            gender=row.gender,
            custom_gender=row.custom_gender,
            height_value=float(row.height_value) if row.height_value is not None else None,
            height_unit=row.height_unit,
            weight_value=float(row.weight_value) if row.weight_value is not None else None,
            weight_unit=row.weight_unit,
            age_range=row.age_range,
            skin_tone=getattr(row, "skin_tone", None),
            undertone=getattr(row, "undertone", None),
            body_types=list(row.body_types or []),
            custom_body_type=row.custom_body_type,
            fit_preferences=list(row.fit_preferences or []),
            custom_fit_notes=row.custom_fit_notes,
            size_profile=dict(row.size_profile or {}),
            custom_size_notes=row.custom_size_notes,
            style_preferences=list(row.style_preferences or []),
            favorite_colors=list(row.favorite_colors or []),
            avoided_colors=list(row.avoided_colors or []),
            neutral_color_preference=row.neutral_color_preference,
            bold_color_preference=row.bold_color_preference,
            occasion_preferences=list(row.occasion_preferences or []),
            climate_preferences=list(row.climate_preferences or []),
            onboarding_completed=row.onboarding_completed,
            onboarding_skipped=row.onboarding_skipped,
            style_summary=getattr(row, "style_summary", None),
            styling_goals=list(getattr(row, "styling_goals", None) or []),
            avoidances=list(getattr(row, "avoidances", None) or []),
            pattern_preferences=list(getattr(row, "pattern_preferences", None) or []),
            style_archetype=getattr(row, "style_archetype", None),
            recommendation_rules=getattr(row, "recommendation_rules", None),
            ai_stylist_context=getattr(row, "ai_stylist_context", None),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool
    onboarding_skipped: bool
    has_profile_record: bool


class CompleteOnboardingBody(BaseModel):
    skipped: bool = False


class OnboardingSubmitBody(BaseModel):
    """Single-call payload for the new v2 onboarding wizard."""

    # Step 1 — Style Identity
    style_preferences: list[str] = Field(default_factory=list)
    # Step 2 — Lifestyle / Occasions
    occasion_preferences: list[str] = Field(default_factory=list)
    # Step 3 — Fit & Comfort
    fit_preferences: list[str] = Field(default_factory=list)
    avoidances: list[str] = Field(default_factory=list)
    # Step 4 — Colors & Patterns
    favorite_colors: list[str] = Field(default_factory=list)
    avoided_colors: list[str] = Field(default_factory=list)
    pattern_preferences: list[str] = Field(default_factory=list)
    # Step 5 — Styling Goal
    styling_goals: list[str] = Field(default_factory=list)
    # Step 6 — Body (optional)
    gender: GenderValue | None = None
    body_types: list[str] = Field(default_factory=list)
    age_range: str | None = Field(None, max_length=40)
    skin_tone: str | None = Field(None, max_length=32)
    undertone: UndertoneValue | None = None
    climate_preferences: list[str] = Field(default_factory=list)


