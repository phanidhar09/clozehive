"""Closet item request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ClosetItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, max_length=100)
    fabric: str | None = Field(None, max_length=100)
    pattern: str | None = Field(None, max_length=100)
    season: str | None = Field(None, max_length=50)
    occasion: list[str] | None = None
    eco_score: float | None = Field(None, ge=0, le=10)
    tags: list[str] | None = None
    image_url: str | None = None
    notes: str | None = None
    brand: str | None = Field(None, max_length=100)
    size: str | None = Field(None, max_length=20)
    price: float | None = Field(None, ge=0)


class ClosetItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    category: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = None
    fabric: str | None = None
    pattern: str | None = None
    season: str | None = None
    occasion: list[str] | None = None
    eco_score: float | None = Field(None, ge=0, le=10)
    tags: list[str] | None = None
    image_url: str | None = None
    notes: str | None = None
    brand: str | None = None
    size: str | None = None
    price: float | None = Field(None, ge=0)
    is_archived: bool | None = None


class ClosetItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    category: str
    color: str | None
    fabric: str | None
    pattern: str | None
    season: str | None
    occasion: list[str] | None
    eco_score: float | None
    tags: list[str] | None
    image_url: str | None
    notes: str | None
    brand: str | None
    size: str | None
    price: float | None
    wear_count: int
    last_worn: date | None
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
    worn_date: date | None = None  # defaults to today


class ClosetUploadResponse(BaseModel):
    """Vision upload — persisted item plus raw vision JSON for the UI."""

    item: ClosetItemResponse
    vision_analysis: dict[str, Any] = Field(default_factory=dict)
