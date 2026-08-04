"""Trip schemas — includes activity-aware travel planner types."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.validators import strip_string

TripPurpose = Literal["leisure", "business", "beach", "formal", "adventure"]
TripStyle = Literal["casual", "smart_casual", "chic", "business", "sporty", "beach", "boho", "streetwear"]
BagSize = Literal["backpack", "carry_on", "medium_suitcase", "large_suitcase", "none"]
TimeOfDay = Literal["morning", "afternoon", "evening", "night", "full_day"]
Formality = Literal["casual", "smart_casual", "formal", "active", "beachwear", "business"]


# ── Activity model ────────────────────────────────────────────────────────────


class TripActivity(BaseModel):
    """A single planned or booked activity for the trip."""

    name: str = Field(..., min_length=1, max_length=100)
    day_number: int | None = Field(None, ge=1, le=30, description="Which day of the trip (1-based)")
    date: str | None = Field(None, description="ISO date string if specific date is known")
    time_of_day: TimeOfDay | None = None
    formality: Formality | None = None
    is_fixed: bool = Field(default=False, description="True if already booked/confirmed")
    notes: str | None = Field(None, max_length=500)

    @field_validator("name", "notes", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v


# ── Trip creation / update ────────────────────────────────────────────────────


class TripCreate(BaseModel):
    destination: str = Field(..., min_length=2, max_length=200)
    start_date: date
    end_date: date
    purpose: TripPurpose
    trip_style: TripStyle | None = None
    bag_size: BagSize | None = None
    notes: str | None = Field(None, max_length=2000)
    activities: list[TripActivity] = Field(default_factory=list)

    @field_validator("destination", "notes", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @model_validator(mode="after")
    def validate_date_range(self):
        today = date.today()
        # Same-day is valid: single-event "occasion" plans send start == end.
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        if self.start_date < today - timedelta(days=365 * 2):
            raise ValueError("Start date cannot be more than 2 years in the past")
        if self.end_date > today + timedelta(days=365 * 5):
            raise ValueError("End date cannot be more than 5 years in the future")
        return self


# ── Trip responses ────────────────────────────────────────────────────────────


class TripResponse(BaseModel):
    id: UUID
    user_id: UUID
    destination: str
    start_date: date
    end_date: date
    purpose: str
    notes: str | None = None
    trip_style: str | None = None
    bag_size: str | None = None
    activities: list[dict[str, Any]] = []
    is_saved: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TripListResponse(BaseModel):
    trips: list[TripResponse]
    total: int


# ── Packing plan schemas ───────────────────────────────────────────────────────


class PackingPlanResponse(BaseModel):
    """Full packing plan — includes both legacy fields and new activity-aware fields."""

    id: UUID
    trip_id: UUID
    user_id: UUID
    # ── Legacy fields (backward compat) ──────────────────────────────────────
    take_from_your_closet: list[dict[str, Any]] = []
    you_might_still_need: list[dict[str, Any]] = []
    daily_plan: list[Any] = []
    weather_summary: dict[str, Any] | None = None
    packing_list: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []
    summary: str | None = None
    closet_hint: str | None = None
    alerts: list[str] = []
    # ── New activity-aware fields ─────────────────────────────────────────────
    activities: list[dict[str, Any]] = []
    day_plans_rich: list[dict[str, Any]] = []
    rewear_strategy: list[dict[str, Any]] = []
    bag_capacity_summary: dict[str, Any] | None = None
    packing_checklist: list[dict[str, Any]] = []
    checklist_state: dict[str, Any] = {}
    trip_style_direction: str | None = None
    climate_summary: str | None = None
    location_etiquette: str | None = None
    # ── User edits ────────────────────────────────────────────────────────────
    # Days the user hand-edited. These are preserved verbatim across a
    # regenerate; the UI badges them so the reshuffle scope is visible.
    pinned_days: list[int] = []
    # ─────────────────────────────────────────────────────────────────────────
    is_saved: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CreateTripResponse(BaseModel):
    """Response for POST /trips — always includes the trip; packing_plan is best-effort."""

    trip: TripResponse
    packing_plan: PackingPlanResponse | None = None
    packing_error: str | None = None


class SavePlannerResponse(BaseModel):
    """Response for POST /trips/{trip_id}/save-planner."""

    message: str
    trip: TripResponse
    packing_plan: PackingPlanResponse


class AddActivitiesRequest(BaseModel):
    """Body for POST /trips/{trip_id}/activities."""

    activities: list[TripActivity] = Field(..., min_length=0)
    replace: bool = Field(default=False, description="If True, replace existing activities; else append")


class ChecklistUpdateRequest(BaseModel):
    """Body for PATCH /trips/{trip_id}/planner/checklist."""

    item_key: str
    is_packed: bool


# ── Plan editing ──────────────────────────────────────────────────────────────

OutfitEditOperation = Literal["add", "remove", "swap"]


class OutfitEditRequest(BaseModel):
    """Body for PATCH /trips/{trip_id}/planner/days/{day_number}/outfits/{slot}."""

    operation: OutfitEditOperation
    closet_item_id: str | None = Field(
        None, description="Item being added, or the replacement in a swap. Required for add/swap."
    )
    replace_item_id: str | None = Field(None, description="Item being replaced (swap) or removed (remove).")

    @model_validator(mode="after")
    def validate_operands(self):
        if self.operation in ("add", "swap") and not self.closet_item_id:
            raise ValueError(f"closet_item_id is required for '{self.operation}'")
        if self.operation == "swap" and not self.replace_item_id:
            raise ValueError("replace_item_id is required for 'swap'")
        if self.operation == "remove" and not (self.replace_item_id or self.closet_item_id):
            raise ValueError("remove requires the id of the item to drop")
        return self


class ChecklistAddRequest(BaseModel):
    """Body for POST /trips/{trip_id}/planner/checklist/items."""

    closet_item_ids: list[str] = Field(..., min_length=1, max_length=30)
    note: str | None = Field(None, max_length=200)


class ClosetSuggestion(BaseModel):
    """An item the user already owns that would fill a gap in the plan."""

    closet_item_id: str
    item_name: str | None = None
    category: str
    image_url: str | None = None
    reason: str


class ClosetSuggestionsResponse(BaseModel):
    suggestions: list[ClosetSuggestion] = []


class RegenerateRequest(BaseModel):
    """Body for POST /trips/{trip_id}/regenerate-packing."""

    keep_pinned_days: bool = Field(
        default=True,
        description="Preserve hand-edited days verbatim and re-plan only the rest. "
        "Set false for a clean rebuild that discards all edits.",
    )
