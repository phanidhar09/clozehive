"""Canonical Pydantic schemas shared across all MCP servers."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    total_days: int
    recommendation: str
    days: list[WeatherDay] = Field(default_factory=list)


# ── Closet ────────────────────────────────────────────────────────────────────

class ClosetItem(BaseModel):
    id: str
    name: str
    category: str
    color: str = ""
    brand: str = ""
    size: str = ""
    occasion: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    wear_count: int = 0
    eco_score: float | None = None
    price: float | None = None
    notes: str | None = None


# ── Vision ────────────────────────────────────────────────────────────────────

class VisionAnalysisResult(BaseModel):
    name: str
    category: str
    color: str
    brand: str = ""
    material: str = ""
    pattern: str = ""
    occasion: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    eco_score: float | None = None
    confidence: float = 1.0
    notes: str = ""


# ── Outfit ────────────────────────────────────────────────────────────────────

class OutfitSuggestion(BaseModel):
    name: str
    items: list[ClosetItem]
    style_notes: str
    occasion_fit: str
    weather_suitability: str
    style_score: float = 0.0


class OutfitResult(BaseModel):
    outfits: list[OutfitSuggestion]
    style_tips: list[str] = Field(default_factory=list)


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
    weather: WeatherDay
    outfit_name: str
    items: list[str]


class PackingResult(BaseModel):
    destination: str
    start_date: str
    end_date: str
    purpose: str
    packing_list: list[PackingItem]
    missing_items: list[PackingItem] = Field(default_factory=list)
    daily_plan: list[DailyOutfitPlan] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    summary: str = ""
