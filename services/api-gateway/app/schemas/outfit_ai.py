"""Pydantic schemas for AI outfit analysis and generation (POST /outfits/generate)."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Shared sub-models ──────────────────────────────────────────────────────────

class OutfitItemRef(BaseModel):
    id: str
    name: str
    category: str
    color: Optional[str] = None


class OutfitItemSlots(BaseModel):
    top: Optional[OutfitItemRef] = None
    bottom: Optional[OutfitItemRef] = None
    footwear: Optional[OutfitItemRef] = None
    outerwear: Optional[OutfitItemRef] = None
    accessories: list[OutfitItemRef] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    color: int = Field(ge=0, le=25, description="Color compatibility (max 25)")
    occasion: int = Field(ge=0, le=25, description="Occasion match (max 25)")
    fit: int = Field(ge=0, le=20, description="Fit & size alignment (max 20)")
    style: int = Field(ge=0, le=15, description="Style consistency (max 15)")
    weather: int = Field(ge=0, le=10, description="Weather suitability (max 10)")
    preference: int = Field(ge=0, le=5, description="User preference match (max 5)")


class OutfitRecommendations(BaseModel):
    improvements: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    styling_tips: list[str] = Field(default_factory=list)


OccasionStyleMatch = Literal["High", "Medium", "Low"]
SizeProfileMatch = Literal["High", "Medium", "Low", "Unknown"]


class ScoredOutfit(BaseModel):
    items: OutfitItemSlots
    matching_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    score_breakdown: ScoreBreakdown
    fit_notes: str = Field(
        default="",
        description="How this outfit suits the user's body profile and preferred fit.",
    )
    fit_confidence: Optional[int] = Field(
        None, ge=0, le=100, description="0–100 fit/size confidence distinct from overall confidence."
    )
    occasion_match: Optional[OccasionStyleMatch] = None
    style_match: Optional[OccasionStyleMatch] = None
    size_profile_match: Optional[SizeProfileMatch] = None
    body_profile_notes: str = Field(
        default="",
        description="Positive, supportive notes referencing fit and silhouette — never judgmental.",
    )
    recommendations: OutfitRecommendations
    reasoning: str = ""
    why_it_works: str = ""
    what_to_improve: list[str] = Field(default_factory=list)


class UnusedItem(BaseModel):
    id: str
    name: str
    category: str
    why_not_selected: str


# ── Request schemas ────────────────────────────────────────────────────────────

class AnalyzeOutfitRequest(BaseModel):
    """Analyse a specific outfit combination already built by the user."""
    item_ids: list[str] = Field(..., min_length=1, description="IDs of the selected closet items")
    occasion: str = Field("casual", max_length=100)
    weather: str = Field("mild", max_length=100)
    temperature: Optional[float] = Field(None, ge=-30, le=55)
    user_profile: Optional[dict] = None
    date: Optional[str] = Field(None, description="ISO date for weather lookup (YYYY-MM-DD)")
    location: Optional[str] = Field(None, max_length=200, description="City/location for real-time weather")


# ── Response schemas ───────────────────────────────────────────────────────────

class AnalyzeOutfitResponse(BaseModel):
    """Single-outfit analysis returned from POST /outfits/generate."""
    outfit: ScoredOutfit
    missing_pieces: list[str] = Field(default_factory=list)
    style_tips: list[str] = Field(default_factory=list)


class GenerateOutfitsResponse(BaseModel):
    """Three generated outfit combinations returned from POST /ai/outfit (enhanced)."""
    outfits: list[ScoredOutfit]
    unused_items: list[UnusedItem] = Field(default_factory=list)
    style_tips: list[str] = Field(default_factory=list)
