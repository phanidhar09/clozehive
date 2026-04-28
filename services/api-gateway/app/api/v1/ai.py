"""
AI routes — /api/v1/ai/*
Proxies requests to the AI agent service after fetching closet context.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AppError, BadRequestError
from app.repositories.closet_repo import ClosetRepository
from app.services import ai_client

router = APIRouter(prefix="/ai", tags=["AI"])

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/heic"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    include_closet: bool = True  # auto-inject the user's closet items


class ChatResponse(BaseModel):
    reply: str


class OutfitRequest(BaseModel):
    occasion: str = "casual"
    weather: str = "mild"
    temperature: float = Field(20.0, ge=-30, le=55)


class PackingRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    purpose: str = "general"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_closet_as_dicts(session: DbSession, user_id: UUID) -> list[dict[str, Any]]:
    repo = ClosetRepository(session)
    items = await repo.get_by_user(user_id, limit=200)
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "category": i.category,
            "color": i.color or "",
            "fabric": i.fabric or "",
            "season": i.season or "",
            "occasion": i.occasion or [],
            "tags": i.tags or [],
        }
        for i in items
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """
    Send a message to the CLOZEHIVE wardrobe AI.
    Automatically injects the user's closet items as context unless include_closet=False.
    """
    closet = await _get_closet_as_dicts(session, UUID(user_id)) if body.include_closet else []
    reply = await ai_client.chat(body.message, history=body.history, closet_items=closet, user_id=user_id)
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """SSE stream of assistant tokens proxied from the AI agent."""

    async def events():
        done = False
        try:
            yield _sse({"type": "status", "message": "Thinking…"})
            closet = await _get_closet_as_dicts(session, UUID(user_id)) if body.include_closet else []
            async for event in ai_client.stream_chat(
                body.message,
                history=body.history,
                closet_items=closet,
                user_id=user_id,
            ):
                if event.get("type") == "status":
                    continue
                if event.get("type") == "done":
                    done = True
                yield _sse(event)
            if not done:
                yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.post("/outfit")
async def outfit(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    """Generate 3 AI outfit suggestions from the user's closet."""
    closet = await _get_closet_as_dicts(session, UUID(user_id))
    return await ai_client.generate_outfits(
        closet, body.occasion, body.weather, body.temperature
    )


@router.post("/outfit/stream")
async def outfit_stream(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    async def events():
        try:
            yield _sse({"type": "status", "message": "Generating outfits…"})
            closet = await _get_closet_as_dicts(session, UUID(user_id))
            data = await ai_client.generate_outfits(
                closet, body.occasion, body.weather, body.temperature
            )
            yield _sse({"type": "result", "data": data})
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.post("/packing")
async def packing(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    """Generate a smart travel packing list matched against the user's closet."""
    closet = await _get_closet_as_dicts(session, UUID(user_id))
    return await ai_client.generate_packing_list(
        body.destination, body.start_date, body.end_date, body.purpose, closet
    )


@router.post("/packing/stream")
async def packing_stream(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    async def events():
        try:
            yield _sse({"type": "status", "message": "Fetching weather…"})
            closet = await _get_closet_as_dicts(session, UUID(user_id))
            data = await ai_client.generate_packing_list(
                body.destination,
                body.start_date,
                body.end_date,
                body.purpose,
                closet,
            )
            yield _sse({"type": "status", "message": "Matching wardrobe…"})
            summary = ""
            if isinstance(data, dict):
                summary = str(data.get("summary") or "")
            step = max(8, min(48, len(summary) // 20 or 8))
            for i in range(0, len(summary), step):
                yield _sse({"type": "token", "content": summary[i : i + step]})
            yield _sse({"type": "status", "message": "AI insights ready"})
            yield _sse({"type": "result", "data": data})
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.post("/vision/analyze")
async def vision_analyze(
    user_id: CurrentUser,
    file: UploadFile = File(...),
):
    """Analyse a garment image with GPT-4o Vision."""
    ct = file.content_type or "image/jpeg"
    if ct not in _ALLOWED_MEDIA:
        raise BadRequestError(f"Unsupported image type: {ct}")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise BadRequestError("Image must be under 10 MB")

    return await ai_client.analyze_image(data, ct)
