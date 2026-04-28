"""
AI feature endpoints — outfit suggestions, travel packing, chat.
Supports both regular JSON responses and SSE streaming.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.deps import DB, CurrentUser
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    OutfitRequest,
    OutfitResponse,
    TravelPackRequest,
    TravelPackResponse,
)
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["AI Stylist"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


# ── Outfit ─────────────────────────────────────────────────────────────────────

@router.post("/outfit", response_model=OutfitResponse)
async def generate_outfit(
    body: OutfitRequest,
    current_user: CurrentUser,
    db: DB,
) -> OutfitResponse:
    """Generate outfit suggestions (JSON response)."""
    return await AIService.generate_outfit(body)


@router.post("/outfit/stream")
async def generate_outfit_stream(
    body: OutfitRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    """
    Generate outfit suggestions as an SSE stream.

    Event types:
      data: {"type": "status",  "message": "..."}
      data: {"type": "token",   "content": "..."}
      data: {"type": "result",  "data": {...}}
      data: {"type": "done"}
    """
    return StreamingResponse(
        AIService.stream_outfit(body),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Travel Packing ─────────────────────────────────────────────────────────────

@router.post("/travel-pack", response_model=TravelPackResponse)
async def generate_packing_list(
    body: TravelPackRequest,
    current_user: CurrentUser,
    db: DB,
) -> TravelPackResponse:
    """Generate a travel packing list (JSON response)."""
    return await AIService.generate_packing_list(body)


# ── Chat ───────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: CurrentUser,
) -> ChatResponse:
    """Single-turn AI chat with optional conversation history."""
    return await AIService.chat(body)
