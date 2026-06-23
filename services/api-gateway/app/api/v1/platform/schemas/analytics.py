"""Analytics schemas for closet insights."""

from __future__ import annotations

from pydantic import BaseModel


class CategoryCoverageItem(BaseModel):
    category: str
    count: int
    recommended_minimum: int
    status: str  # "good" | "low" | "missing"


class ClosetSummary(BaseModel):
    total_items: int
    strongest_category: str | None
    most_common_color: str | None
    best_covered_occasion: str | None


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


class CostPerWearItem(BaseModel):
    """An item ranked by cost-per-wear (price ÷ times worn)."""

    item_id: str
    name: str
    category: str
    price: float
    wear_count: int
    cost_per_wear: float


class ForgottenGem(BaseModel):
    """A priced item that's gone unworn — a candidate to resurface."""

    item_id: str
    name: str
    category: str
    wear_count: int
    last_worn: str | None = None  # ISO date
    days_since_worn: int | None = None  # None == never worn


class VersatilityItem(BaseModel):
    """How many saved outfits an item appears in."""

    item_id: str
    name: str
    category: str
    outfit_count: int


class WardrobeValueInsights(BaseModel):
    """The money/usage layer, derived from price + wear history.

    Item lists carry no image URL on purpose — the client resolves images from
    its already-loaded (and signed) closet store by item_id, so analytics never
    has to re-sign URLs.
    """

    items_priced: int  # how many items have a price (denominator for value math)
    total_value: float  # sum of known prices
    value_worn: float  # value of items worn at least once
    value_unworn: float  # value sitting unused
    utilization_rate: float  # % of items worn at least once (0–100)
    active_rate_90d: float  # % of items worn in the last 90 days (0–100)
    avg_cost_per_wear: float | None  # across priced + worn items
    best_value_items: list[CostPerWearItem] = []  # lowest cost-per-wear
    worst_value_items: list[CostPerWearItem] = []  # highest cost-per-wear (worn ≥1)
    forgotten_gems: list[ForgottenGem] = []  # unworn / long-unworn
    most_versatile: list[VersatilityItem] = []  # appear in the most outfits


class PurchaseGapInsight(BaseModel):
    """A wardrobe gap identified by the RAG purchase-gap detector."""

    gap_type: str
    missing_category: str
    reason: str
    priority_score: float
    suggested_attributes: dict | None = None


class DigestItem(BaseModel):
    """One highlighted item in the weekly recap, with a human-readable detail."""

    item_id: str
    name: str
    category: str
    detail: str  # e.g. "worn 3× this week" or "92 days ago"


class WeeklyDigest(BaseModel):
    """'Your Week in Style' — a scheduled return trigger, computed from the last
    7 days of wear_events plus the closet rollup. Deterministic (no LLM) so it's
    cheap and reliable to render on every dashboard load."""

    week_start: str  # ISO date (inclusive)
    week_end: str  # ISO date (inclusive, == today)
    wears_logged: int  # wear events in the window
    items_worn: int  # distinct items worn
    new_items: int  # items added in the window
    utilization_rate: float  # current % of closet worn at least once
    most_worn: DigestItem | None = None
    best_value: DigestItem | None = None  # lowest cost-per-wear among items worn this week
    forgotten_gem: DigestItem | None = None  # one piece to revive
    headline: str  # one computed sentence summarizing the week


class ClosetAnalyticsResponse(BaseModel):
    summary: ClosetSummary
    category_coverage: list[CategoryCoverageItem]
    color_stats: list[ColorStats]
    category_stats: list[CategoryStats]
    outfit_readiness: OutfitReadiness
    usage_insights: UsageInsights | None = None
    value_insights: WardrobeValueInsights | None = None
    purchase_gap_insights: list[PurchaseGapInsight] = []
