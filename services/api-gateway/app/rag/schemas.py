"""
Pydantic schemas for /api/v1/rag/* endpoints.

Request and response models are kept in this file so the router and any
downstream consumers share a single source of truth for the contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Shared sub-models ─────────────────────────────────────────────────────────


class FashionDoc(BaseModel):
    id: str
    title: str
    content: str
    category: str
    season: str | None = None
    occasion: str | None = None
    relevance_score: float


class OutfitHistoryRecord(BaseModel):
    id: str
    occasion: str | None
    weather_context: dict[str, Any] | None
    selected_item_ids: list[str]
    matching_score: int | None
    recommendation_text: str | None
    improvement_tips: list[str]
    was_saved: bool
    was_worn: bool
    user_feedback: str | None
    similarity_score: float
    created_at: str


class PackingMemoryRecord(BaseModel):
    id: str
    destination: str
    purpose: str | None
    start_date: str | None
    end_date: str | None
    weather_summary: dict[str, Any] | None
    packed_item_ids: list[str]
    missing_items: list[dict[str, Any]]
    user_feedback: str | None
    similarity_score: float
    created_at: str


class SimilarItemRecord(BaseModel):
    item_id: str
    name: str
    category: str
    color: str
    brand: str
    image_url: str
    similarity_score: float
    reason: str


class PurchaseGapRecord(BaseModel):
    id: str
    gap_type: str
    missing_category: str
    missing_color: str | None
    missing_season: str | None
    missing_occasion: str | None
    reason: str
    priority_score: float
    source_context: dict[str, Any] | None
    suggested_attributes: dict[str, Any] | None
    resolved: bool
    created_at: str | None


# ── /rag/outfit-context ───────────────────────────────────────────────────────


class OutfitContextResponse(BaseModel):
    occasion: str
    weather: str
    fashion_knowledge: list[FashionDoc] = Field(default_factory=list)
    outfit_history: list[OutfitHistoryRecord] = Field(default_factory=list)
    has_context: bool
    fallback_message: str | None = None


# ── /rag/packing-context ─────────────────────────────────────────────────────


class PackingContextResponse(BaseModel):
    destination: str
    purpose: str
    packing_history: list[PackingMemoryRecord] = Field(default_factory=list)
    has_context: bool
    fallback_message: str | None = None


# ── /rag/similar-items ────────────────────────────────────────────────────────


class SimilarItemsRequest(BaseModel):
    closet_item_id: str | None = None
    query: str | None = None
    image_url: str | None = None
    limit: int = Field(5, ge=1, le=20)


class SimilarItemsResponse(BaseModel):
    query_type: Literal["closet_item", "text_query", "image_url", "none"]
    query_ref: str | None
    count: int
    results: list[SimilarItemRecord]
    has_results: bool


# ── /rag/purchase-gaps ────────────────────────────────────────────────────────


class PurchaseGapsResponse(BaseModel):
    count: int
    gaps: list[PurchaseGapRecord]
    has_gaps: bool
    summary: str
