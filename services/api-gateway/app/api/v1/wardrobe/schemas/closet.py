"""Closet item request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.validators import strip_string

ClosetCategory = Literal["tops", "bottoms", "shoes", "outerwear", "dresses", "accessories", "other"]

_CANONICAL_CATEGORIES = frozenset(
    {
        "tops",
        "bottoms",
        "shoes",
        "outerwear",
        "dresses",
        "accessories",
        "other",
    }
)

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


# ── Shared season normalizer ─────────────────────────────────────────────────


def _coerce_str_list(v: Any) -> list[str]:
    """Normalise any season value into a deduplicated list of lowercase strings.

    Handles all formats the API or AI layer might send:
    - None / ""         → []
    - "summer"          → ["summer"]
    - "summer, spring"  → ["summer", "spring"]
    - ["summer", "spring"] → ["summer", "spring"]
    """
    if v is None:
        return []
    if isinstance(v, str):
        parts = [s.strip().lower() for s in v.split(",") if s.strip()]
    elif isinstance(v, (list, tuple)):
        parts = [str(s).strip().lower() for s in v if s and str(s).strip()]
    else:
        return []
    # Deduplicate while preserving order
    seen: set[str] = set()
    return [x for x in parts if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]


def _coerce_str_list_optional(v: Any) -> list[str] | None:
    """Variant for update payloads: None means 'do not change'; [] means 'clear'."""
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        # Empty string from update payload → treat as "no change" (consistent with
        # how other string fields behave when blanked in a PATCH request).
        return None
    return _coerce_str_list(v)


# ── Request schemas ───────────────────────────────────────────────────────────


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

    @field_validator(
        "name",
        "color",
        "fabric",
        "pattern",
        "image_url",
        "original_image_url",
        "processed_image_url",
        "notes",
        "brand",
        "size",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("season", mode="before")
    @classmethod
    def coerce_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

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
    name: str | None = Field(None, min_length=1, max_length=200)
    category: ClosetCategory | None = None
    color: str | None = Field(None, max_length=50)
    fabric: str | None = Field(None, max_length=100)
    pattern: str | None = Field(None, max_length=100)
    season: list[str] | None = None
    occasion: list[str] | None = Field(None, max_length=10)
    eco_score: float | None = Field(None, ge=0, le=10)
    tags: list[str] | None = Field(None, max_length=20)
    image_url: str | None = None
    notes: str | None = Field(None, max_length=1000)
    brand: str | None = Field(None, max_length=100)
    size: str | None = Field(None, max_length=20)
    price: float | None = Field(None, ge=0, le=99999.99)
    is_archived: bool | None = None

    @field_validator("name", "color", "fabric", "pattern", "image_url", "notes", "brand", "size", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("season", mode="before")
    @classmethod
    def coerce_season(cls, v: Any) -> list[str] | None:
        return _coerce_str_list_optional(v)

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
        # ORM may return None for rows that had no season before the migration.
        return _coerce_str_list(v)

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


# ── Preview → confirm upload flow (no DB rows until POST /closet/confirm) ─────


class ClosetPreviewItem(BaseModel):
    """One detected item from analyze-preview — canonical, frontend-stable shape."""

    slot_index: int = Field(..., ge=0)
    temp_id: str = Field(..., description="Stable id for this detection within the session (alias of legacy item_id).")
    detected_item_id: str | None = Field(
        None, description="UUID assigned immediately after detection; stable across crop/BG/metadata pipeline."
    )
    name: str
    category: str
    subcategory: str | None = None
    color: str | None = None
    brand: str | None = None
    material: str | None = None
    pattern: str | None = None
    season: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    description: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    original_image_url: str
    preview_image_url: str
    processed_image_url: str | None = None
    background_removed: bool = False
    background_removal_status: str | None = None
    style_tags: list[str] = Field(default_factory=list)

    @field_validator(
        "name", "category", "subcategory", "color", "brand", "material", "pattern", "description", mode="before"
    )
    @classmethod
    def strip_prev_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("season", mode="before")
    @classmethod
    def prev_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("occasions", mode="before")
    @classmethod
    def prev_occ(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if x and str(x).strip()]
        return []

    @field_validator("style_tags", mode="before")
    @classmethod
    def prev_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            t = v.strip()
            return [t] if t else []
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if x and str(x).strip()]
        return []


class ClosetAnalyzePreviewResponse(BaseModel):
    preview_session_id: UUID
    items: list[ClosetPreviewItem]
    scan_id: str | None = None
    pipeline_cached: bool = False


class ClosetConfirmItemPayload(BaseModel):
    slot_index: int = Field(..., ge=0)
    detected_item_id: str | None = Field(
        None,
        description="Stable UUID from detection. Backend cross-checks this against the stored slot to catch frontend ordering bugs.",
    )
    selected: bool = True
    name: str = Field(..., min_length=1, max_length=200)
    category: ClosetCategory
    color: str | None = Field(None, max_length=50)
    fabric: str | None = Field(None, max_length=100)
    material: str | None = Field(None, max_length=100)
    pattern: str | None = Field(None, max_length=100)
    season: list[str] = Field(default_factory=list)
    occasion: list[str] | None = Field(None, max_length=10)
    notes: str | None = Field(None, max_length=1000)
    brand: str | None = Field(None, max_length=100)
    size: str | None = Field(None, max_length=20)
    price: float | None = Field(None, ge=0, le=99999.99)
    tags: list[str] | None = Field(None, max_length=20)
    eco_score: float | None = Field(None, ge=0, le=10)

    @field_validator("name", "color", "fabric", "material", "pattern", "notes", "brand", "size", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @field_validator("season", mode="before")
    @classmethod
    def coerce_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

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


class ClosetConfirmRequest(BaseModel):
    preview_session_id: UUID
    items: list[ClosetConfirmItemPayload]


class ClosetConfirmResponse(BaseModel):
    saved: list[ClosetItemResponse]
    total_saved: int


class BulkPreviewFailure(BaseModel):
    filename: str
    error: str


class BulkAnalyzePreviewFileResult(BaseModel):
    filename: str
    preview: ClosetAnalyzePreviewResponse


class BulkAnalyzePreviewResponse(BaseModel):
    results: list[BulkAnalyzePreviewFileResult]
    failed: list[BulkPreviewFailure] = Field(default_factory=list)


# ── Vision Pipeline schemas ───────────────────────────────────────────────────


class NormalizedBoundingBox(BaseModel):
    """Bounding box relative to full source image: origin + size (all 0–1)."""

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., ge=0.0, le=1.0)
    height: float = Field(..., ge=0.0, le=1.0)


class VisionAnalysisItem(BaseModel):
    """One detected clothing item from the vision pipeline (before saving)."""

    # Stable UUID assigned immediately after detection — source of truth for image↔metadata correlation.
    detected_item_id: str = ""
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
    failed_items: list[dict[str, Any]] = Field(default_factory=list)


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
