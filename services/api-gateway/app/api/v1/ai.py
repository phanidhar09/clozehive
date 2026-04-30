"""
AI routes — /api/v1/ai/*
Proxies requests to the AI agent service after fetching closet context from Firestore.
Postgres session is only needed for async routes that track requests via create_request.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AppError, BadRequestError
from app.events import producer as event_producer, topics
from app.events.schemas import AsyncAcceptedResponse, EventEnvelope
from app.repositories.user_repo import UserRepository
from app.services import ai_client
from app.services.ai_request_service import create_request
from app.services.firestore.closet_service import FirestoreClosetService

router = APIRouter(prefix="/ai", tags=["AI"])

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/heic"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    include_closet: bool = True


class ChatResponse(BaseModel):
    reply: str


class OutfitRequest(BaseModel):
    occasion: str = "casual"
    weather: str = "mild"
    temperature: float = Field(20.0, ge=-30, le=55)
    # Optional client-side override; if absent we load profile from DB.
    user_profile: dict[str, Any] | None = None


class PackingRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    purpose: str = "general"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_closet_as_dicts(user_id: UUID) -> list[dict[str, Any]]:
    svc = FirestoreClosetService()
    return await svc.get_all_for_ai(user_id, limit=200)


async def _resolve_user_profile(
    session, user_id: UUID, override: dict[str, Any] | None
) -> dict[str, Any] | None:
    """
    Build the personalization context passed to the AI agent.

    Client-supplied `override` wins (lets the UI temporarily tune a request);
    otherwise we read the persisted profile from Postgres. Returns None when
    there is nothing useful to send so the agent can fall back to defaults.
    """
    if override:
        return override
    user = await UserRepository(session).get(user_id)
    if user is None:
        return None
    profile = {
        "body_profile":  user.body_profile,
        "style_profile": user.style_profile,
        "preferences":   user.preferences,
    }
    # Drop empty/null sections so the prompt stays compact.
    profile = {k: v for k, v in profile.items() if v}
    return profile or None


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user_id: CurrentUser):
    """Send a message to the CLOZEHIVE wardrobe AI."""
    closet = await _get_closet_as_dicts(UUID(user_id)) if body.include_closet else []
    reply = await ai_client.chat(body.message, history=body.history, closet_items=closet, user_id=user_id)
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user_id: CurrentUser):
    """SSE stream of assistant tokens proxied from the AI agent."""

    async def events():
        done = False
        try:
            yield _sse({"type": "status", "message": "Thinking…"})
            closet = await _get_closet_as_dicts(UUID(user_id)) if body.include_closet else []
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


@router.post("/chat/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat_async(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """Publish an async AI chat job; tokens are delivered through ai_response_stream events."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(user_uuid) if body.include_closet else []
    payload = {"message": body.message, "history": body.history, "closet_items": closet}
    await create_request(
        session,
        request_id=request_id,
        user_id=user_uuid,
        request_type=topics.AI_CHAT_REQUESTED,
        input_payload=payload,
    )
    await session.commit()
    await event_producer.publish(
        topics.AI_CHAT_REQUESTED,
        EventEnvelope(event_type=topics.AI_CHAT_REQUESTED, request_id=request_id, user_id=user_uuid, payload=payload),
    )
    return AsyncAcceptedResponse(request_id=request_id, event_type=topics.AI_CHAT_REQUESTED, message="AI chat queued")


# ── Outfit ────────────────────────────────────────────────────────────────────

@router.post("/outfit")
async def outfit(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    """Generate 3 AI outfit suggestions from the user's closet."""
    uid = UUID(user_id)
    closet = await _get_closet_as_dicts(uid)
    profile = await _resolve_user_profile(session, uid, body.user_profile)
    return await ai_client.generate_outfits(
        closet, body.occasion, body.weather, body.temperature, user_profile=profile,
    )


@router.post("/outfit/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def outfit_async(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    """Publish an outfit generation job and return immediately."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(user_uuid)
    profile = await _resolve_user_profile(session, user_uuid, body.user_profile)
    payload = {
        "closet_items": closet,
        "occasion": body.occasion,
        "weather": body.weather,
        "temperature": body.temperature,
        "user_profile": profile,
    }
    await create_request(session, request_id=request_id, user_id=user_uuid, request_type=topics.OUTFIT_REQUESTED, input_payload=payload)
    await session.commit()
    await event_producer.publish(
        topics.OUTFIT_REQUESTED,
        EventEnvelope(event_type=topics.OUTFIT_REQUESTED, request_id=request_id, user_id=user_uuid, payload=payload),
    )
    return AsyncAcceptedResponse(request_id=request_id, event_type=topics.OUTFIT_REQUESTED, message="Outfit generation queued")


@router.post("/outfit/stream")
async def outfit_stream(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    uid = UUID(user_id)

    async def events():
        try:
            yield _sse({"type": "status", "message": "Generating outfits…"})
            closet = await _get_closet_as_dicts(uid)
            profile = await _resolve_user_profile(session, uid, body.user_profile)
            data = await ai_client.generate_outfits(
                closet, body.occasion, body.weather, body.temperature, user_profile=profile,
            )
            yield _sse({"type": "result", "data": data})
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


# ── Packing ───────────────────────────────────────────────────────────────────

@router.post("/packing")
async def packing(body: PackingRequest, user_id: CurrentUser):
    """Generate a smart travel packing list matched against the user's closet."""
    closet = await _get_closet_as_dicts(UUID(user_id))
    return await ai_client.generate_packing_list(body.destination, body.start_date, body.end_date, body.purpose, closet)


@router.post("/packing/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def packing_async(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    """Publish a trip planning/packing job and return immediately."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(user_uuid)
    payload = {
        "destination": body.destination,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "purpose": body.purpose,
        "closet_items": closet,
    }
    await create_request(session, request_id=request_id, user_id=user_uuid, request_type=topics.TRIP_PLANNED, input_payload=payload)
    await session.commit()
    await event_producer.publish(
        topics.TRIP_PLANNED,
        EventEnvelope(event_type=topics.TRIP_PLANNED, request_id=request_id, user_id=user_uuid, payload=payload),
    )
    return AsyncAcceptedResponse(request_id=request_id, event_type=topics.TRIP_PLANNED, message="Trip packing plan queued")


@router.post("/packing/stream")
async def packing_stream(body: PackingRequest, user_id: CurrentUser):
    async def events():
        try:
            yield _sse({"type": "status", "message": "Fetching weather…"})
            closet = await _get_closet_as_dicts(UUID(user_id))
            data = await ai_client.generate_packing_list(
                body.destination, body.start_date, body.end_date, body.purpose, closet
            )
            yield _sse({"type": "status", "message": "Matching wardrobe…"})
            summary = str(data.get("summary") or "") if isinstance(data, dict) else ""
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


# ── Vision ────────────────────────────────────────────────────────────────────

@router.post("/vision/analyze")
async def vision_analyze(user_id: CurrentUser, file: UploadFile = File(...)):
    """Analyse a garment image with GPT-4o Vision."""
    ct = file.content_type or "image/jpeg"
    if ct not in _ALLOWED_MEDIA:
        raise BadRequestError(f"Unsupported image type: {ct}")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise BadRequestError("Image must be under 10 MB")
    return await ai_client.analyze_image(data, ct)
