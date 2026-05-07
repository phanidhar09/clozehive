"""Trip schemas for MVP travel planner."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.validators import strip_string

TripPurpose = Literal["leisure", "business", "beach", "formal", "adventure"]


class TripCreate(BaseModel):
    destination: str = Field(..., min_length=2, max_length=200)
    start_date: date
    end_date: date
    purpose: TripPurpose
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("destination", "notes", mode="before")
    @classmethod
    def strip_strings(cls, v: str | None) -> str | None:
        return strip_string(v) if v is not None else v

    @model_validator(mode="after")
    def validate_date_range(self):
        today = date.today()
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after start date")
        if self.start_date < today - timedelta(days=365 * 2):
            raise ValueError("Start date cannot be more than 2 years in the past")
        if self.end_date > today + timedelta(days=365 * 5):
            raise ValueError("End date cannot be more than 5 years in the future")
        return self


class TripResponse(BaseModel):
    id: UUID
    user_id: UUID
    destination: str
    start_date: date
    end_date: date
    purpose: str
    notes: Optional[str] = None
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
    """Stored packing plan returned alongside a trip."""
    id: UUID
    trip_id: UUID
    user_id: UUID
    take_from_your_closet: list[dict[str, Any]] = []
    you_might_still_need: list[dict[str, Any]] = []
    daily_plan: list[Any] = []
    weather_summary: Optional[dict[str, Any]] = None
    # Full backward-compatible packing result for the frontend
    packing_list: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []
    summary: Optional[str] = None
    closet_hint: Optional[str] = None
    alerts: list[str] = []
    is_saved: bool = False
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CreateTripResponse(BaseModel):
    """Response for POST /trips — always includes the trip; packing_plan is best-effort."""
    trip: TripResponse
    packing_plan: Optional[PackingPlanResponse] = None
    packing_error: Optional[str] = None


class SavePlannerResponse(BaseModel):
    """Response for POST /trips/{trip_id}/save-planner."""
    message: str
    trip: TripResponse
    packing_plan: PackingPlanResponse
