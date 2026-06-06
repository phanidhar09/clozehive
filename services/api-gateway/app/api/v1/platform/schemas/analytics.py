"""Analytics schemas for closet insights."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CategoryCoverageItem(BaseModel):
    category: str
    count: int
    recommended_minimum: int
    status: str  # "good" | "low" | "missing"


class ClosetSummary(BaseModel):
    total_items: int
    strongest_category: Optional[str]
    most_common_color: Optional[str]
    best_covered_occasion: Optional[str]


class ColorStats(BaseModel):
    color: str
    count: int
    percentage: float


class CategoryStats(BaseModel):
    category: str
    count: int
    percentage: float


class OutfitReadiness(BaseModel):
    estimated_outfits: int
    best_covered_occasions: list[str]
    weakest_covered_occasions: list[str]


class UsageInsights(BaseModel):
    most_worn_items: list[dict]
    least_worn_items: list[dict]
    not_worn_recently: list[dict]


class PurchaseGapInsight(BaseModel):
    """A wardrobe gap identified by the RAG purchase-gap detector."""
    gap_type: str
    missing_category: str
    reason: str
    priority_score: float
    suggested_attributes: Optional[dict] = None


class ClosetAnalyticsResponse(BaseModel):
    summary: ClosetSummary
    category_coverage: list[CategoryCoverageItem]
    color_stats: list[ColorStats]
    category_stats: list[CategoryStats]
    outfit_readiness: OutfitReadiness
    usage_insights: Optional[UsageInsights] = None
    purchase_gap_insights: list[PurchaseGapInsight] = []
