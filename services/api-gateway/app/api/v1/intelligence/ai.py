"""
AI routes — /api/v1/ai/*
Proxies requests to the AI agent service after fetching closet context from Firestore.
Postgres session is only needed for async routes that track requests via create_request.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.intelligence.services import ai_service, festival_calendar
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.travel.services import packing_service, weather_service
from app.api.v1.travel.services.location_intel_service import build_location_context_block
from app.api.v1.wardrobe.services import outfit_service, vision_service
from app.api.v1.wardrobe.services.outfit_history_service import get_outfit_history_for_prompt
from app.core import cache_service
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.embedding_service import generate_text_embedding, pgvector_cosine_search
from app.core.exceptions import AIServiceError, AppError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.upload_service import read_validated_image
from app.models.closet import ClosetItem
from app.models.trips import Trip

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
    # True when the reply is a graceful fallback because the AI stylist was
    # unavailable (circuit open / timeout). UI can show a soft "offline" hint.
    degraded: bool = False


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
    notes: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

# Trivial messages that never need wardrobe context. Skipping the closet load for
# these avoids an embedding API call + pgvector query on every greeting/ack.
_TRIVIAL_CHAT_MESSAGES = frozenset(
    {
        "hi",
        "hii",
        "hey",
        "hello",
        "yo",
        "sup",
        "hiya",
        "thanks",
        "thank you",
        "thx",
        "ty",
        "thank u",
        "cheers",
        "ok",
        "okay",
        "k",
        "cool",
        "nice",
        "great",
        "got it",
        "gotcha",
        "bye",
        "goodbye",
        "see ya",
        "good night",
        "gn",
        "yes",
        "no",
        "yeah",
        "nope",
        "yep",
        "sure",
    }
)


def _message_needs_closet(message: str) -> bool:
    """Heuristic: does this chat message warrant loading wardrobe context?

    Returns False for short greetings/acknowledgements so we skip the embedding
    + pgvector retrieval. Conservative — anything longer than a few words, or
    containing wardrobe-related keywords, always loads the closet.
    """
    normalized = message.strip().lower().rstrip("!.?")
    if normalized in _TRIVIAL_CHAT_MESSAGES:
        return False
    # Very short messages (≤ 2 words) with no wardrobe keyword → skip.
    if len(normalized.split()) <= 2:
        wardrobe_keywords = (
            "wear",
            "outfit",
            "closet",
            "wardrobe",
            "style",
            "dress",
            "shirt",
            "pants",
            "shoes",
            "look",
            "fit",
            "color",
            "match",
        )
        if not any(kw in normalized for kw in wardrobe_keywords):
            return False
    return True


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
    session,
    user_id: UUID,
    occasion: str,
    weather_cond: str = "mild",
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    """RAG-aware closet loader: vector search first, fallback to wear_count.

    Pass an explicit ``query_text`` when the caller has already built a search
    phrase (e.g. packing). Otherwise an occasion label is wrapped in the default
    template — passing a full phrase as ``occasion`` produces a garbled query.
    """
    if query_text is None:
        query_text = f"outfit for {occasion} occasion weather:{weather_cond}"
    embedding = await generate_text_embedding(query_text)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=str(user_id),
            limit=30,
            threshold=0.25,
            filter_archived=True,
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


async def _resolve_user_profile(session, user_id: UUID, override: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Build personalization context for AI routes (legacy JSONB + dedicated style profile).
    Client-supplied `override` wins so the UI can temporarily tune a request.
    """
    return await load_merged_user_profile_for_ai(session, user_id, override)


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _location_prompt_block(weather: dict[str, Any] | None) -> str:
    if not weather:
        return ""
    label = weather.get("location_label")
    if not label:
        return ""
    block = build_location_context_block(str(label), mode="daily")
    return f"\n\n{block}" if block else ""


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
            "You are a personal AI stylist for ClozeHive. This user has not added any wardrobe items yet. "
            "Give general fashion advice and encourage them to upload their wardrobe items using the Smart "
            f"Closet Scan feature.{profile_block}{_weather_prompt_block(weather)}{_location_prompt_block(weather)}"
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
    return f"""You are a personal AI stylist for ClozeHive. The user's complete wardrobe is listed below. When suggesting outfits or styling advice:
- ONLY recommend items from the wardrobe list below
- Always refer to items by their EXACT name as listed
- If the wardrobe lacks a suitable item for an outfit component, explicitly say so rather than inventing items
- Consider the occasions listed for each item when making recommendations
- Always factor in the user's style profile, body type, fit preferences, and color palette when present

[WARDROBE CONTEXT]
{closet_context}
[END WARDROBE CONTEXT]{profile_block}{_weather_prompt_block(weather)}{_location_prompt_block(weather)}"""


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
    # RAG-aware closet: embed the user message and retrieve semantically relevant
    # items — but skip the embedding + pgvector call for trivial greetings/acks.
    load_closet = body.include_closet and _message_needs_closet(body.message)
    closet = await _get_closet_for_occasion(session, uid, body.message) if load_closet else []
    weather, user_profile = await asyncio.gather(
        _resolve_weather_context(session, uid),
        _resolve_user_profile(session, uid, None),
    )
    # Fetch fashion knowledge relevant to this message
    fashion_ctx = ""
    try:
        fashion_ctx = await get_fashion_context_for_prompt(session, body.message)
    except Exception as exc:
        logger.warning("fashion_context_unavailable", error=str(exc))
    messages = _chat_messages(body)
    cache_key = cache_service.build_cache_key(
        user_id,
        messages,
        cache_service.build_closet_hash(closet),
        cache_service.build_profile_hash(user_profile),
    )

    async def _compute_reply() -> str:
        system_prompt = _build_stylist_system_prompt(closet, weather, user_profile)
        if fashion_ctx.strip():
            system_prompt += f"\n\n[FASHION KNOWLEDGE]\n{fashion_ctx.strip()}\n[END FASHION KNOWLEDGE]"
        return await ai_service.chat(messages, system_prompt)

    # Degrade gracefully: if the AI stylist is down (circuit open / timeout /
    # unreachable) return a friendly fallback instead of a 502, so the chat UI
    # stays usable. Not cached — we want to retry the real AI on the next message.
    try:
        if settings.ai_cache_enabled:
            # Single-flight + stale-while-revalidate: under a burst of identical
            # questions only one request hits the LLM; the rest serve cache/stale.
            reply = await cache_service.get_or_compute(
                cache_key,
                settings.ai_cache_ttl,
                _compute_reply,
                swr_seconds=settings.ai_cache_ttl,
            )
            return ChatResponse(reply=reply)
        return ChatResponse(reply=await _compute_reply())
    except (ServiceUnavailableError, AIServiceError) as exc:
        logger.warning("chat_degraded_fallback", user_id=user_id, error=str(exc))
        return ChatResponse(
            reply=(
                "I'm having a brief hiccup reaching the styling brain right now. "
                "Try again in a moment — in the meantime, a safe bet is to pair a "
                "neutral top with your most-worn bottoms and a layer you can remove."
            ),
            degraded=True,
        )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user_id: CurrentUser, session: DbSession):
    """SSE stream of assistant tokens proxied from the AI agent."""

    async def events():
        try:
            yield _sse({"type": "status", "message": "Thinking…"})
            uid = UUID(user_id)
            # RAG-aware: embed the message and retrieve relevant closet items —
            # skip the embedding + pgvector call for trivial greetings/acks.
            load_closet = body.include_closet and _message_needs_closet(body.message)
            closet = await _get_closet_for_occasion(session, uid, body.message) if load_closet else []
            weather, user_profile = await asyncio.gather(
                _resolve_weather_context(session, uid),
                _resolve_user_profile(session, uid, None),
            )
            fashion_ctx = ""
            try:
                fashion_ctx = await get_fashion_context_for_prompt(session, body.message)
            except Exception as exc:
                logger.warning("fashion_context_unavailable", error=str(exc))
            messages = _chat_messages(body)
            cache_key = cache_service.build_cache_key(
                user_id,
                messages,
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
            system_prompt = _build_stylist_system_prompt(closet, weather, user_profile)
            if fashion_ctx.strip():
                system_prompt += f"\n\n[FASHION KNOWLEDGE]\n{fashion_ctx.strip()}\n[END FASHION KNOWLEDGE]"
            async for chunk in ai_service.stream_chat(messages, system_prompt):
                full_response.append(chunk)
                yield _sse({"type": "token", "content": chunk})
            if settings.ai_cache_enabled:
                await cache_service.cache_response(
                    await get_redis(), cache_key, "".join(full_response), settings.ai_cache_ttl
                )
            yield _sse({"type": "done"})
        except AppError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers=_STREAM_HEADERS)


# ── Outfit ────────────────────────────────────────────────────────────────────


@router.post("/outfit")
async def outfit(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    """Generate 3 AI outfit suggestions from the user's closet."""
    uid = UUID(user_id)
    # RAG: load only occasion-relevant items + fetch fashion/history context
    closet = await _get_closet_for_occasion(session, uid, body.occasion, body.weather)
    profile = await _resolve_user_profile(session, uid, body.user_profile)
    rag_query = f"outfit for {body.occasion} weather:{body.weather or 'mild'}"
    fashion_ctx, history_ctx = await asyncio.gather(
        get_fashion_context_for_prompt(session, rag_query),
        get_outfit_history_for_prompt(session, user_id, body.occasion),
        return_exceptions=True,
    )
    return await outfit_service.generate_outfits(
        closet,
        body.occasion,
        body.weather,
        body.temperature,
        user_profile=profile,
        fashion_context=fashion_ctx if isinstance(fashion_ctx, str) else "",
        history_context=history_ctx if isinstance(history_ctx, str) else "",
    )


@router.post("/outfit/stream")
async def outfit_stream(body: OutfitRequest, user_id: CurrentUser, session: DbSession):
    uid = UUID(user_id)

    async def events():
        try:
            yield _sse({"type": "status", "message": "Generating outfits…"})
            # RAG: vector-filtered closet + fashion knowledge + outfit history
            closet = await _get_closet_for_occasion(session, uid, body.occasion, body.weather)
            profile = await _resolve_user_profile(session, uid, body.user_profile)
            rag_query = f"outfit for {body.occasion} weather:{body.weather or 'mild'}"
            fashion_ctx, history_ctx = await asyncio.gather(
                get_fashion_context_for_prompt(session, rag_query),
                get_outfit_history_for_prompt(session, user_id, body.occasion),
                return_exceptions=True,
            )
            data = await outfit_service.generate_outfits(
                closet,
                body.occasion,
                body.weather,
                body.temperature,
                user_profile=profile,
                fashion_context=fashion_ctx if isinstance(fashion_ctx, str) else "",
                history_context=history_ctx if isinstance(history_ctx, str) else "",
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
    cached = await cache_service.get(cache_key)
    if cached is not None:
        logger.info("outfit_of_day_cache_hit", user_id=user_id, date=today)
        return cached

    # ── Generate ──────────────────────────────────────────────────────────────
    weekday = datetime.utcnow().weekday()  # 0=Mon … 6=Sun
    occasion = "business" if weekday < 5 else "casual"

    # Run sequentially rather than concurrently: both coroutines share the same
    # SQLAlchemy session, and asyncio.gather with return_exceptions=True swallows
    # Python exceptions but DOES NOT roll back the Postgres transaction.  If either
    # call left the session in a failed-transaction state the next query would raise
    # InFailedSQLTransactionError.  Sequential calls keep the session clean.
    weather: dict | None = None
    profile: dict | None = None
    try:
        weather = await _resolve_weather_context(session, uid)
    except Exception as exc:
        logger.warning("outfit_weather_failed", error=str(exc))
        await session.rollback()

    try:
        profile = await _resolve_user_profile(session, uid, None)
    except Exception as exc:
        logger.warning("outfit_profile_failed", error=str(exc))
        await session.rollback()

    weather_str = weather.get("condition", "mild") if weather else "mild"
    temp = float(weather.get("temp_c", 20.0)) if weather else 20.0

    # Festival awareness — when today is a festival at the user's location, dress
    # for the festival instead of the default weekday occasion. If the user is
    # mid-trip, the destination wins over home so travellers get destination
    # festivals (static calendar only — OOTD needs a clean occasion label).
    festival_payload: dict | None = None
    try:
        today_date = datetime.utcnow().date()
        festival_location = (weather or {}).get("location_label")
        active_trip = (
            await session.execute(
                select(Trip)
                .where(
                    Trip.user_id == uid,
                    Trip.start_date <= today_date,
                    Trip.end_date >= today_date,
                )
                .order_by(Trip.start_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if active_trip:
            festival_location = active_trip.destination
        country = festival_calendar.infer_country(festival_location)
        todays = festival_calendar.festivals_on(country, today_date)
        if todays:
            festival = todays[0]
            occasion = festival_calendar.festival_occasion(festival)
            festival_payload = {
                "name": festival["name"],
                "emoji": festival["emoji"],
                "dress": festival["dress"],
            }
            logger.info("outfit_of_day_festival", user_id=user_id, festival=festival["name"])
    except Exception as exc:  # noqa: BLE001 — festival layer is best-effort
        logger.warning("outfit_festival_failed", error=str(exc))
        await session.rollback()

    # RAG: load only occasion-relevant items via vector search
    closet = await _get_closet_for_occasion(session, uid, occasion, weather_str)

    result = await outfit_service.generate_outfits(
        closet,
        occasion,
        weather_str,
        temp,
        user_profile=profile,
    )
    outfits = result.get("outfits") or []
    payload = {
        "outfit": outfits[0] if outfits else None,
        "weather": weather,
        "occasion": occasion,
        "festival": festival_payload,
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
    # RAG: load closet relevant to destination+purpose, inject fashion/packing knowledge
    rag_query = f"packing for {body.destination} trip purpose:{body.purpose}"
    closet = await _get_closet_for_occasion(session, uid, body.purpose, query_text=rag_query)
    prof = await load_merged_user_profile_for_ai(session, uid, None)
    packing_ctx = ""
    try:
        packing_ctx = await get_fashion_context_for_prompt(session, rag_query)
    except Exception as exc:
        logger.warning("fashion_context_unavailable", error=str(exc))
    return await packing_service.generate_packing_list(
        body.destination,
        body.start_date,
        body.end_date,
        body.purpose,
        closet,
        notes=body.notes,
        user_style_profile=prof,
        rag_context=packing_ctx or None,
    )


@router.post("/packing/stream")
async def packing_stream(body: PackingRequest, user_id: CurrentUser, session: DbSession):
    async def events():
        try:
            yield _sse({"type": "status", "message": "Fetching weather…"})
            uid = UUID(user_id)
            # RAG: vector-filtered closet + fashion/packing knowledge context
            rag_query = f"packing for {body.destination} trip purpose:{body.purpose}"
            closet = await _get_closet_for_occasion(session, uid, body.purpose, query_text=rag_query)
            prof = await load_merged_user_profile_for_ai(session, uid, None)
            packing_ctx = ""
            try:
                packing_ctx = await get_fashion_context_for_prompt(session, rag_query)
            except Exception as exc:
                logger.warning("fashion_context_unavailable", error=str(exc))
            data = await packing_service.generate_packing_list(
                body.destination,
                body.start_date,
                body.end_date,
                body.purpose,
                closet,
                notes=body.notes,
                user_style_profile=prof,
                rag_context=packing_ctx or None,
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
