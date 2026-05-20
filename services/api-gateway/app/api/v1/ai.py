"""
AI routes — /api/v1/ai/*
Proxies requests to the AI agent service after fetching closet context from Firestore.
Postgres session is only needed for async routes that track requests via create_request.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AppError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.config import get_settings
from app.core.redis import get_redis
from app.events import producer as event_producer, topics
from app.events.schemas import AsyncAcceptedResponse, EventEnvelope
from app.models.closet import ClosetItem
from app.repositories.user_repo import UserRepository
from app.services.style_profile_context import load_merged_user_profile_for_ai
from app.services import ai_service, cache_service, outfit_service, packing_service, vision_service, weather_service
from app.services.embedding_service import generate_text_embedding, pgvector_cosine_search
from app.services.ai_request_service import create_request
from app.services.upload_service import read_validated_image

router = APIRouter(prefix="/ai", tags=["AI"])
logger = get_logger("ai.routes")
settings = get_settings()

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
    user_profile: Optional[dict[str, Any]] = None


class PackingRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    purpose: str = "general"
    notes: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_dict(item: ClosetItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "name": item.name,
        "category": item.category,
        "color": item.color or "",
        "occasion": item.occasion or [],
        "season": item.season or "",
        "wear_count": item.wear_count,
    }


async def _get_closet_for_occasion(
    session, user_id: UUID, occasion: str, weather_cond: str = "mild"
) -> list[dict[str, Any]]:
    """RAG-aware closet loader: vector search first, fallback to wear_count."""
    query_text = f"outfit for {occasion} occasion weather:{weather_cond}"
    embedding = await generate_text_embedding(query_text)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=str(user_id),
            extra_where="AND is_archived = false",
            limit=30,
            threshold=0.25,
        )
        if rows:
            return [
                {
                    "id": str(r["id"]),
                    "name": r.get("name") or "",
                    "category": r.get("category") or "",
                    "color": r.get("color") or "",
                    "occasion": r.get("occasion") or [],
                    "season": r.get("season") or "",
                    "wear_count": r.get("wear_count") or 0,
                }
                for r in rows
            ]
    # Fallback when no embeddings exist yet
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(50)
    )
    return [_item_dict(item) for item in result.scalars().all()]


async def _resolve_user_profile(
    session, user_id: UUID, override: Optional[dict[str, Any]]
) -> dict[str, Any] | None:
    """
    Build personalization context for AI routes (legacy JSONB + dedicated style profile).
    Client-supplied `override` wins so the UI can temporarily tune a request.
    """
    return await load_merged_user_profile_for_ai(session, user_id, override)


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _weather_prompt_block(weather: dict[str, Any] | None) -> str:
    if not weather:
        return ""
    label = weather.get("location_label") or "your location"
    return f"""

[CURRENT WEATHER at {label}]
Condition: {weather.get("condition")}
Temperature: {weather.get("temp_c")}°C / {weather.get("temp_f")}°F
Feels like: {weather.get("feels_like_c")}°C
Humidity: {weather.get("humidity")}%
[END WEATHER]

Factor this weather into outfit recommendations. Suggest layering if needed. Mention weather suitability explicitly."""


async def _resolve_weather_context(session, user_id: UUID) -> dict[str, Any] | None:
    user = await UserRepository(session).get(user_id)
    permissions = user.permissions if user else None
    if not isinstance(permissions, dict) or not permissions.get("location"):
        return None
    try:
        coords = permissions.get("location_coords")
        label = permissions.get("location_label")
        if isinstance(coords, dict) and coords.get("lat") is not None and coords.get("lon") is not None:
            return await weather_service.get_current_weather(float(coords["lat"]), float(coords["lon"]), label)
        if label:
            return await weather_service.get_weather_by_city(str(label))
    except Exception as exc:
        # Weather is helpful context, but chat should never fail because it is unavailable.
        logger.warning("weather_context_unavailable", error=str(exc), user_id=str(user_id))
    return None


def _build_stylist_system_prompt(
    closet_items: list[dict[str, Any]],
    weather: dict[str, Any] | None = None,
    user_profile: dict[str, Any] | None = None,
) -> str:
    profile_block = ""
    if user_profile:
        profile_context = user_profile.get("style_profile_context_text") or ""
        if profile_context:
            profile_block = f"\n\n[USER STYLE PROFILE]\n{profile_context}\n[END USER STYLE PROFILE]"

    if not closet_items:
        return (
            "You are a personal AI stylist for ClosetIQ. This user has not added any wardrobe items yet. "
            "Give general fashion advice and encourage them to upload their wardrobe items using the Smart "
            f"Closet Scan feature.{profile_block}{_weather_prompt_block(weather)}"
        )

    lines = [f"USER'S WARDROBE ({len(closet_items)} items):"]
    for item in closet_items:
        occasions = item.get("occasion") or []
        occasion_text = ", ".join(str(o) for o in occasions) if isinstance(occasions, list) else str(occasions)
        lines.append(
            f"- {item.get('name', 'Unnamed item')} | {item.get('category', 'uncategorised')} | "
            f"{item.get('color') or 'unknown'} | {occasion_text}"
        )
    closet_context = "\n".join(lines)
    return f"""You are a personal AI stylist for ClosetIQ. The user's complete wardrobe is listed below. When suggesting outfits or styling advice:
- ONLY recommend items from the wardrobe list below
- Always refer to items by their EXACT name as listed
- If the wardrobe lacks a suitable item for an outfit component, explicitly say so rather than inventing items
- Consider the occasions listed for each item when making recommendations
- Always factor in the user's style profile, body type, fit preferences, and color palette when present

[WARDROBE CONTEXT]
{closet_context}
[END WARDROBE CONTEXT]{profile_block}{_weather_prompt_block(weather)}"""


def _chat_messages(body: ChatRequest) -> list[dict[str, str]]:
    return [*body.history, {"role": "user", "content": body.message}]


_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """Send a message to the CLOZEHIVE wardrobe AI."""
    uid = UUID(user_id)
    closet = await _get_closet_as_dicts(session, uid) if body.include_closet else []
    weather, user_profile = await asyncio.gather(
        _resolve_weather_context(session, uid),
        _resolve_user_profile(session, uid, None),
    )
    messages = _chat_messages(body)
    cache_key = cache_service.build_cache_key(
        user_id, messages,
        cache_service.build_closet_hash(closet),
        cache_service.build_profile_hash(user_profile),
    )
    if settings.ai_cache_enabled:
        redis = await get_redis()
        cached = await cache_service.get_cached_response(redis, cache_key)
        if cached is not None:
            logger.info("AI cache hit", user_id=user_id, key=cache_key)
            return ChatResponse(reply=cached)
        logger.info("AI cache miss", user_id=user_id, key=cache_key)
    reply = await ai_service.chat(messages, _build_stylist_system_prompt(closet, weather, user_profile))
    if settings.ai_cache_enabled:
        await cache_service.cache_response(await get_redis(), cache_key, reply, settings.ai_cache_ttl)
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """SSE stream of assistant tokens proxied from the AI agent."""

    async def events():
        done = False
        try:
            yield _sse({"type": "status", "message": "Thinking…"})
            uid = UUID(user_id)
            closet = await _get_closet_as_dicts(session, uid) if body.include_closet else []
            weather, user_profile = await asyncio.gather(
                _resolve_weather_context(session, uid),
                _resolve_user_profile(session, uid, None),
            )
            messages = _chat_messages(body)
            cache_key = cache_service.build_cache_key(
                user_id, messages,
                cache_service.build_closet_hash(closet),
                cache_service.build_profile_hash(user_profile),
            )
            if settings.ai_cache_enabled:
                redis = await get_redis()
                cached = await cache_service.get_cached_response(redis, cache_key)
                if cached is not None:
                    logger.info("AI cache hit", user_id=user_id, key=cache_key)
                    yield _sse({"type": "token", "content": cached, "cache": "HIT"})
                    yield _sse({"type": "done"})
                    return
                logger.info("AI cache miss", user_id=user_id, key=cache_key)
            full_response = []
            async for chunk in ai_service.stream_chat(messages, _build_stylist_system_prompt(closet, weather, user_profile)):
                full_response.append(chunk)
                yield _sse({"type": "token", "content": chunk})
            if settings.ai_cache_enabled:
                await cache_service.cache_response(await get_redis(), cache_key, "".join(full_response), settings.ai_cache_ttl)
            done = True
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.post("/chat/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat_async(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    if not settings.kafka_enabled:
        raise ServiceUnavailableError("Async processing requires Kafka — not available in this deployment")
    """Publish an async AI chat job; tokens are delivered through ai_response_stream events."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(session, user_uuid) if body.include_closet else []
    payload = {"message": body.message, "history": body.history, "closet_items": closet}
    await create_request(
        session,
        request_id=request_id,
        user_id=user_uuid,
        request_type=topics.AI_CHAT_REQUESTED,
        input_payload=payload,
    )
    # Commit before Kafka so workers read a committed ai_requests row (see app.db.session).
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
    closet = await _get_closet_as_dicts(session, uid)
    profile = await _resolve_user_profile(session, uid, body.user_profile)
    return await outfit_service.generate_outfits(
        closet, body.occasion, body.weather, body.temperature, user_profile=profile,
    )


@router.post("/outfit/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def outfit_async(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    if not settings.kafka_enabled:
        raise ServiceUnavailableError("Async processing requires Kafka — not available in this deployment")
    """Publish an outfit generation job and return immediately."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(session, user_uuid)
    profile = await _resolve_user_profile(session, user_uuid, body.user_profile)
    payload = {
        "closet_items": closet,
        "occasion": body.occasion,
        "weather": body.weather,
        "temperature": body.temperature,
        "user_profile": profile,
    }
    await create_request(session, request_id=request_id, user_id=user_uuid, request_type=topics.OUTFIT_REQUESTED, input_payload=payload)
    # Commit before Kafka so workers read a committed ai_requests row (see app.db.session).
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
            closet = await _get_closet_as_dicts(session, uid)
            profile = await _resolve_user_profile(session, uid, body.user_profile)
            data = await outfit_service.generate_outfits(
                closet, body.occasion, body.weather, body.temperature, user_profile=profile,
            )
            yield _sse({"type": "result", "data": data})
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


# ── Outfit of the Day ────────────────────────────────────────────────────────

def _seconds_until_midnight_utc() -> int:
    """Seconds remaining until 00:00 UTC — used as the daily cache TTL."""
    now = datetime.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    midnight += timedelta(days=1)
    return max(60, int((midnight - now).total_seconds()))


@router.get("/outfit-of-day")
async def outfit_of_day(user_id: CurrentUser, session: DbSession):
    """
    Return a single AI-generated outfit for today based on the user's closet,
    current weather at their saved location, and day-of-week occasion.

    The result is cached in Redis until midnight UTC so the same outfit is
    returned on every page reload throughout the day.
    """
    uid = UUID(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cache_key = cache_service.namespaced_key("outfit-of-day", str(uid), today)

    # ── Cache hit ─────────────────────────────────────────────────────────────
    redis = await get_redis()
    cached = await cache_service.get(cache_key)
    if cached is not None:
        logger.info("outfit_of_day_cache_hit", user_id=user_id, date=today)
        return cached

    # ── Generate ──────────────────────────────────────────────────────────────
    weekday = datetime.utcnow().weekday()  # 0=Mon … 6=Sun
    occasion = "business" if weekday < 5 else "casual"

    weather, profile = await asyncio.gather(
        _resolve_weather_context(session, uid),
        _resolve_user_profile(session, uid, None),
        return_exceptions=True,
    )
    if isinstance(weather, Exception):
        weather = None
    if isinstance(profile, Exception):
        profile = None

    weather_str = weather.get("condition", "mild") if weather else "mild"
    temp = float(weather.get("temp_c", 20.0)) if weather else 20.0

    # RAG: load only occasion-relevant items via vector search
    closet = await _get_closet_for_occasion(session, uid, occasion, weather_str)

    result = await outfit_service.generate_outfits(
        closet, occasion, weather_str, temp, user_profile=profile,
    )
    outfits = result.get("outfits") or []
    payload = {
        "outfit": outfits[0] if outfits else None,
        "weather": weather,
        "occasion": occasion,
        "style_tips": result.get("style_tips") or [],
    }

    # ── Cache until midnight UTC ──────────────────────────────────────────────
    ttl = _seconds_until_midnight_utc()
    await cache_service.set(cache_key, payload, ttl)
    logger.info("outfit_of_day_cached", user_id=user_id, date=today, ttl_seconds=ttl)

    return payload


# ── Packing ───────────────────────────────────────────────────────────────────

@router.post("/packing")
async def packing(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    """Generate a smart travel packing list matched against the user's closet."""
    uid = UUID(user_id)
    closet = await _get_closet_as_dicts(session, uid)
    prof = await load_merged_user_profile_for_ai(session, uid, None)
    return await packing_service.generate_packing_list(
        body.destination,
        body.start_date,
        body.end_date,
        body.purpose,
        closet,
        notes=body.notes,
        user_style_profile=prof,
    )


@router.post("/packing/async", response_model=AsyncAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def packing_async(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    if not settings.kafka_enabled:
        raise ServiceUnavailableError("Async processing requires Kafka — not available in this deployment")
    """Publish a trip planning/packing job and return immediately."""
    request_id = uuid4()
    user_uuid = UUID(user_id)
    closet = await _get_closet_as_dicts(session, user_uuid)
    payload = {
        "destination": body.destination,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "purpose": body.purpose,
        "notes": body.notes,
        "closet_items": closet,
    }
    await create_request(session, request_id=request_id, user_id=user_uuid, request_type=topics.TRIP_PLANNED, input_payload=payload)
    # Commit before Kafka so workers read a committed ai_requests row (see app.db.session).
    await session.commit()
    await event_producer.publish(
        topics.TRIP_PLANNED,
        EventEnvelope(event_type=topics.TRIP_PLANNED, request_id=request_id, user_id=user_uuid, payload=payload),
    )
    return AsyncAcceptedResponse(request_id=request_id, event_type=topics.TRIP_PLANNED, message="Trip packing plan queued")


@router.post("/packing/stream")
async def packing_stream(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    async def events():
        try:
            yield _sse({"type": "status", "message": "Fetching weather…"})
            uid = UUID(user_id)
            closet = await _get_closet_as_dicts(session, uid)
            prof = await load_merged_user_profile_for_ai(session, uid, None)
            data = await packing_service.generate_packing_list(
                body.destination,
                body.start_date,
                body.end_date,
                body.purpose,
                closet,
                notes=body.notes,
                user_style_profile=prof,
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
    """Analyse a garment image with Claude Vision."""
    logger.info("vision_analyze_request", user_id=user_id)
    image_bytes, content_type = await read_validated_image(file)
    return await vision_service.analyze_image(image_bytes, content_type)
