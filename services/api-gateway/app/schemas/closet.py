"""Closet item request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.validators import strip_string

ClosetCategory = Literal["tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other"]


class ClosetItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: ClosetCategory
    color: Optional[str] = Field(None, max_length=50)
    fabric: Optional[str] = Field(None, max_length=100)
    pattern: Optional[str] = Field(None, max_length=100)
    season: Optional[str] = Field(None, max_length=50)
    occasion: Optional[list[str]] = Field(None, max_length=10)
    eco_score: Optional[float] = Field(None, ge=0, le=10)
    tags: Optional[list[str]] = Field(None, max_length=20)
    image_url: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)
    brand: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=20)
    price: Optional[float] = Field(None, ge=0, le=99999.99)

    @field_validator("name", "color", "fabric", "pattern", "season", "image_url", "notes", "brand", "size", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("tags", "occasion", mode="before")
    @classmethod
    def strip_string_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return [strip_string(item) for item in v if strip_string(item)]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v and any(len(tag) > 50 for tag in v):
            raise ValueError("Each tag must be 50 characters or fewer")
        return v


class ClosetItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[ClosetCategory] = None
    color: Optional[str] = Field(None, max_length=50)
    fabric: Optional[str] = Field(None, max_length=100)
    pattern: Optional[str] = Field(None, max_length=100)
    season: Optional[str] = Field(None, max_length=50)
    occasion: Optional[list[str]] = Field(None, max_length=10)
    eco_score: Optional[float] = Field(None, ge=0, le=10)
    tags: Optional[list[str]] = Field(None, max_length=20)
    image_url: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)
    brand: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=20)
    price: Optional[float] = Field(None, ge=0, le=99999.99)
    is_archived: Optional[bool] = None

    @field_validator("name", "color", "fabric", "pattern", "season", "image_url", "notes", "brand", "size", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("tags", "occasion", mode="before")
    @classmethod
    def strip_string_lists(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return [strip_string(item) for item in v if strip_string(item)]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v and any(len(tag) > 50 for tag in v):
            raise ValueError("Each tag must be 50 characters or fewer")
        return v


class ClosetItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    category: str
    color: Optional[str]
    fabric: Optional[str]
    pattern: Optional[str]
    season: Optional[str]
    occasion: Optional[list[str]]
    eco_score: Optional[float]
    tags: Optional[list[str]]
    image_url: Optional[str]
    notes: Optional[str]
    brand: Optional[str]
    size: Optional[str]
    price: Optional[float]
    wear_count: int
    last_worn: Optional[date]
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClosetListResponse(BaseModel):
    items: list[ClosetItemResponse]
    total: int
    page: int
    per_page: int


class LogWearRequest(BaseModel):
    worn_date: Optional[date] = None  # defaults to today


class ClosetUploadResponse(BaseModel):
    """Vision upload — persisted item plus raw vision JSON for the UI."""

    item: ClosetItemResponse
    vision_analysis: dict[str, Any] = Field(default_factory=dict)
