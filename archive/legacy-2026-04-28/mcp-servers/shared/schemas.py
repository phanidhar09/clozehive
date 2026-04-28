"""
Canonical Pydantic schemas shared across all MCP servers.
All MCP tools serialize their return values to JSON strings using these models.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ── Closet ────────────────────────────────────────────────────────────────────

class ClosetItem(BaseModel):
    id: str | None = None
    user_id: str | None = None
    name: str
    category: str
    color: str = ""
    fabric: str = ""
    pattern: str = ""
    season: str = ""
    occasion: list[str] = Field(default_factory=list)
    eco_score: float = 5.0
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    notes: str = ""
    brand: str = ""
    size: str = ""
    price: float = 0.0
    wear_count: int = 0
    last_worn: str | None = None


# ── Vision ────────────────────────────────────────────────────────────────────

class VisionAnalysisResult(BaseModel):
    garment_type: str
    fabric: str
    color_primary: str
    color_secondary: str
    pattern: str
    season: str
    occasion: list[str] = Field(default_factory=list)
    care_instructions: list[str] = Field(default_factory=list)
    wearing_tips: list[str] = Field(default_factory=list)
    eco_score: int = Field(ge=1, le=10, default=5)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    raw_description: str = ""


# ── Outfit ────────────────────────────────────────────────────────────────────

class OutfitSuggestion(BaseModel):
    name: str
    item_ids: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str
    style_score: int = Field(ge=1, le=10, default=7)
    occasion_fit: str = ""
    weather_fit: str = ""


class OutfitResult(BaseModel):
    outfits: list[OutfitSuggestion]
    occasion: str
    weather: str
    temperature: float


# ── Weather ───────────────────────────────────────────────────────────────────

class WeatherDay(BaseModel):
    date: str
    condition: str
    temp_high: float
    temp_low: float
    description: str


class WeatherSummary(BaseModel):
    dominant_condition: str
    avg_high: float
    avg_low: float
    rainy_days: int
    recommendation: str
    days: list[WeatherDay] = Field(default_factory=list)


# ── Packing ───────────────────────────────────────────────────────────────────

class PackingItem(BaseModel):
    name: str
    category: str
    quantity: int = 1
    reason: str = ""
    available_in_closet: bool = False
    closet_item_id: str | None = None


class DailyOutfitPlan(BaseModel):
    date: str
    weather: str
    outfit_suggestion: str
    items_needed: list[str] = Field(default_factory=list)


class PackingResult(BaseModel):
    destination: str
    start_date: str
    end_date: str
    duration_days: int
    trip_type: str
    weather_summary: dict[str, Any] = Field(default_factory=dict)
    packing_list: list[PackingItem] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)
    daily_plan: list[DailyOutfitPlan] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    packing_item_ids: list[str] = Field(default_factory=list)
