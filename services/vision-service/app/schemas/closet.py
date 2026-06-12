"""Closet item request/response schemas for vision-service."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


ClosetCategory = Literal["tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other"]

_CANONICAL_CATEGORIES = frozenset({
    "tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other",
})

_CATEGORY_ALIASES: dict[str, ClosetCategory] = {
    "top": "tops",
    "shirt": "tops",
    "blouse": "tops",
    "t-shirt": "tops",
    "tee": "tops",
    "sweater": "tops",
    "hoodie": "tops",
    "cardigan": "tops",
    "tank": "tops",
    "polo": "tops",
    "bottom": "bottoms",
    "pants": "bottoms",
    "jeans": "bottoms",
    "trousers": "bottoms",
    "shorts": "bottoms",
    "skirt": "bottoms",
    "leggings": "bottoms",
    "shoe": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "heels": "shoes",
    "sandals": "shoes",
    "loafers": "shoes",
    "coat": "outerwear",
    "jacket": "outerwear",
    "blazer": "outerwear",
    "parka": "outerwear",
    "vest": "outerwear",
    "dress": "dresses",
    "gown": "dresses",
    "jumpsuit": "dresses",
    "bag": "accessories",
    "belt": "accessories",
    "hat": "accessories",
    "scarf": "accessories",
    "jewelry": "accessories",
    "watch": "accessories",
    "sunglasses": "accessories",
    "uncategorised": "other",
    "uncategorized": "other",
    "unknown": "other",
    "general": "other",
    "misc": "other",
    "clothing": "other",
}


def coerce_closet_category(category: str | None) -> ClosetCategory:
    """Normalise vision or form input into a valid closet category."""
    if not category or not str(category).strip():
        return "other"
    c = str(category).strip().lower()
    if c in _CANONICAL_CATEGORIES:
        return cast(ClosetCategory, c)
    return _CATEGORY_ALIASES.get(c, "other")


def _coerce_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        parts = [s.strip().lower() for s in v.split(",") if s.strip()]
    elif isinstance(v, (list, tuple)):
        parts = [str(s).strip().lower() for s in v if s and str(s).strip()]
    else:
        return []
    seen: set[str] = set()
    return [x for x in parts if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]


# ── Response schema ───────────────────────────────────────────────────────────

class ClosetItemResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    category: str
    color: str | None
    fabric: str | None
    pattern: str | None
    season: list[str] = Field(default_factory=list)
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

    original_image_url: str | None = None
    processed_image_url: str | None = None
    background_removed: bool = False
    background_removal_status: str | None = None
    analysis_source: str | None = None
    confidence_score: float | None = None
    scan_batch_id: str | None = None

    @field_validator("season", mode="before")
    @classmethod
    def coerce_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    model_config = {"from_attributes": True}


# ── ClosetItemCreate ──────────────────────────────────────────────────────────

class ClosetItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: ClosetCategory
    color: str | None = Field(None, max_length=50)
    fabric: str | None = Field(None, max_length=100)
    pattern: str | None = Field(None, max_length=100)
    season: list[str] = Field(default_factory=list)
    occasion: list[str] | None = Field(None, max_length=10)
    eco_score: float | None = Field(None, ge=0, le=10)
    tags: list[str] | None = Field(None, max_length=20)
    image_url: str | None = None
    notes: str | None = Field(None, max_length=1000)
    brand: str | None = Field(None, max_length=100)
    size: str | None = Field(None, max_length=20)
    price: float | None = Field(None, ge=0, le=99999.99)

    original_image_url: str | None = None
    processed_image_url: str | None = None
    background_removed: bool = False
    background_removal_status: str | None = Field(None, max_length=20)
    analysis_source: str | None = Field(None, max_length=50)
    confidence_score: float | None = Field(None, ge=0)
    scan_batch_id: str | None = Field(None, max_length=36)

    @field_validator("season", mode="before")
    @classmethod
    def coerce_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


# ── Vision Pipeline schemas ───────────────────────────────────────────────────

class NormalizedBoundingBox(BaseModel):
    """Bounding box relative to full source image: origin + size (all 0–1)."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., ge=0.0, le=1.0)
    height: float = Field(..., ge=0.0, le=1.0)


class VisionAnalysisItem(BaseModel):
    """One detected clothing item from the vision pipeline (before saving)."""

    item_id: str
    category: str
    subcategory: str | None = None
    name: str
    description: str | None = None
    gender: str = "unisex"
    fit: str | None = None
    sleeve_type: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    brand: str | None = None
    occasions: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)

    bounding_box: NormalizedBoundingBox | None = None

    image_base64: str | None = None
    processed_image: str | None = None
    original_image_url: str | None = None

    confidence_score: float = 0.0
    background_removed: bool = False
    background_removal_status: str = "not_attempted"

    segmentation_quality: str | None = None


class VisionAnalyzeResponse(BaseModel):
    """Response from POST /analyze-vision."""

    scan_id: str
    total_items_detected: int
    items: list[VisionAnalysisItem]
    processing_time_ms: int
    cached: bool = False


class SaveItemRequest(BaseModel):
    """Payload for a single item in the save-analyzed-items request."""

    item_id: str
    category: str
    subcategory: str | None = None
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    primary_color: str | None = Field(None, max_length=50)
    secondary_color: str | None = Field(None, max_length=50)
    pattern: str | None = Field(None, max_length=100)
    material: str | None = Field(None, max_length=100)
    brand: str | None = Field(None, max_length=100)
    fit: str | None = Field(None, max_length=50)
    season: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)

    image_base64: str | None = None
    original_image_url: str | None = None

    confidence_score: float = 0.0
    background_removed: bool = False
    background_removal_status: str = "not_attempted"
    scan_batch_id: str | None = None


class SaveAnalyzedItemsRequest(BaseModel):
    items: list[SaveItemRequest]
    scan_batch_id: str | None = None
    save_permission: bool = False


class SaveAnalyzedItemsResponse(BaseModel):
    saved: list[ClosetItemResponse]
    failed: list[dict[str, Any]] = Field(default_factory=list)
    total_saved: int
    total_failed: int
