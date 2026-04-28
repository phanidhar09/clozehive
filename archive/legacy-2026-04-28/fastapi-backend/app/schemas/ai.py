"""
AI feature request/response schemas.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ── Outfit ────────────────────────────────────────────────────────────────────

class OutfitItem(BaseModel):
    name: str
    category: str
    color: Optional[str] = None
    why: Optional[str] = None


class OutfitSuggestion(BaseModel):
    name: str
    items: List[OutfitItem]
    style_notes: Optional[str] = None


class OutfitRequest(BaseModel):
    occasion: str = Field(..., examples=["casual Friday", "job interview", "date night"])
    weather: Optional[str] = Field(None, examples=["sunny 25°C", "rainy 12°C"])
    preferences: Optional[str] = Field(None, examples=["minimalist, neutral colours"])
    closet_items: Optional[List[dict]] = None  # forwarded to AI service


class OutfitResponse(BaseModel):
    outfits: List[OutfitSuggestion]
    explanation: str
    missing_items: List[str] = []


# ── Travel Packing ────────────────────────────────────────────────────────────

class PackingCategory(BaseModel):
    category: str
    items: List[str]


class TravelPackRequest(BaseModel):
    destination: str = Field(..., examples=["Tokyo, Japan"])
    duration_days: int = Field(..., ge=1, le=365)
    activities: Optional[List[str]] = Field(None, examples=[["hiking", "city tour", "beach"]])
    weather: Optional[str] = None
    closet_items: Optional[List[dict]] = None


class TravelPackResponse(BaseModel):
    destination: str
    duration_days: int
    packing_list: List[PackingCategory]
    ai_tips: str
    total_items: int


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = []
    closet_context: Optional[List[dict]] = None


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
