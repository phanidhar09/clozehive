"""Outfit History RAG service.

Saves AI-generated outfit results and retrieves similar past outfits
to improve future recommendations.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.rag import OutfitHistory
from app.services.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.rag.query_builder import build_outfit_history_query
from app.rag.rerank import rerank_outfit_history

logger = get_logger("outfit_history_service")


def _outfit_context_text(
    occasion: str,
    weather: str,
    item_names: list[str],
    score: int | None,
) -> str:
    """Build a searchable text description of an outfit context."""
    parts = [f"Occasion: {occasion}"]
    if weather:
        parts.append(f"Weather: {weather}")
    if item_names:
        parts.append(f"Items: {', '.join(item_names[:10])}")
    if score:
        parts.append(f"Score: {score}")
    return ". ".join(parts)


async def save_outfit_history(
    session: AsyncSession,
    user_id: str,
    occasion: str,
    weather: str,
    selected_item_ids: list[str],
    item_names: list[str],
    matching_score: int | None,
    recommendation_text: str | None,
    improvement_tips: list[str] | None,
) -> OutfitHistory | None:
    """Persist an AI outfit result to outfit_history. Returns the saved record."""
    try:
        context_text = _outfit_context_text(occasion, weather, item_names, matching_score)
        embedding = await generate_text_embedding(context_text)

        record = OutfitHistory(
            user_id=uuid.UUID(user_id),
            occasion=occasion,
            weather_context={"weather": weather} if weather else None,
            selected_item_ids=selected_item_ids,
            matching_score=matching_score,
            recommendation_text=recommendation_text,
            improvement_tips=improvement_tips or [],
            embedding=embedding,
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        logger.info("outfit_history_saved", user_id=user_id, occasion=occasion, score=matching_score)
        return record
    except Exception as exc:
        logger.warning("outfit_history_save_failed", error=str(exc), user_id=user_id)
        return None


async def save_outfit_history_background(
    user_id: str,
    occasion: str,
    weather: str,
    selected_item_ids: list[str],
    item_names: list[str],
    matching_score: int | None,
    recommendation_text: str | None,
    improvement_tips: list[str] | None,
) -> None:
    """Background-task variant — opens its own DB session."""
    async with AsyncSessionLocal() as session:
        await save_outfit_history(
            session=session,
            user_id=user_id,
            occasion=occasion,
            weather=weather,
            selected_item_ids=selected_item_ids,
            item_names=item_names,
            matching_score=matching_score,
            recommendation_text=recommendation_text,
            improvement_tips=improvement_tips,
        )
        await session.commit()


async def search_similar_outfit_history(
    session: AsyncSession,
    user_id: str,
    occasion: str | None = None,
    weather: str = "",
    limit: int = _DEFAULT_LIMIT,
    message: str = "",
) -> list[dict[str, Any]]:
    """Retrieve past outfit history similar to the requested occasion/weather."""
    query_text = build_outfit_history_query(
        occasion=occasion, weather=weather, message=message
    )
    embedding = await generate_text_embedding(query_text)
    if not embedding:
        return []

    fetch_limit = min(max(limit * 3, limit), 15)
    rows = await pgvector_cosine_search(
        session,
        table="outfit_history",
        embedding=embedding,
        user_id=user_id,
        limit=fetch_limit,
        threshold=0.60,
    )
    records = [
        {
            "id": str(r["id"]),
            "occasion": r.get("occasion"),
            "weather_context": r.get("weather_context"),
            "selected_item_ids": r.get("selected_item_ids") or [],
            "matching_score": r.get("matching_score"),
            "recommendation_text": r.get("recommendation_text"),
            "improvement_tips": r.get("improvement_tips") or [],
            "was_saved": r.get("was_saved", False),
            "was_worn": r.get("was_worn", False),
            "user_feedback": r.get("user_feedback"),
            "similarity_score": round(float(r.get("similarity_score", 0)), 3),
            "created_at": str(r.get("created_at", "")),
        }
        for r in rows
    ]
    reranked = rerank_outfit_history(records, occasion=occasion)
    return reranked[:limit]


async def get_outfit_history_for_prompt(
    session: AsyncSession,
    user_id: str,
    occasion: str | None = None,
    weather: str = "",
    limit: int = 3,
    message: str = "",
) -> str:
    """Return a formatted prompt string with relevant past outfit history."""
    history = await search_similar_outfit_history(
        session,
        user_id,
        occasion=occasion,
        weather=weather,
        limit=limit,
        message=message,
    )
    if not history:
        return ""
    lines = ["[Past Outfit History — similar occasions]"]
    for h in history:
        score = h.get("matching_score")
        saved = "✓ saved" if h.get("was_saved") else ""
        worn = "✓ worn" if h.get("was_worn") else ""
        flags = ", ".join(f for f in [saved, worn] if f)
        tip = h.get("user_feedback") or ""
        lines.append(
            f"• Occasion: {h.get('occasion')} | Score: {score} | {flags}"
            + (f" | Feedback: {tip[:100]}" if tip else "")
        )
    return "\n".join(lines)


async def update_outfit_feedback(
    session: AsyncSession,
    history_id: str,
    user_id: str,
    feedback: str | None = None,
    was_worn: bool | None = None,
    was_saved: bool | None = None,
) -> dict[str, Any] | None:
    """Apply user feedback to an outfit history record."""
    record = await session.get(OutfitHistory, uuid.UUID(history_id))
    if not record or str(record.user_id) != user_id:
        return None

    if feedback is not None:
        record.user_feedback = feedback
    if was_worn is not None:
        record.was_worn = was_worn
    if was_saved is not None:
        record.was_saved = was_saved

    await session.flush()
    return {
        "id": str(record.id),
        "user_feedback": record.user_feedback,
        "was_worn": record.was_worn,
        "was_saved": record.was_saved,
    }


async def delete_outfit_history(
    session: AsyncSession,
    history_id: str,
    user_id: str,
) -> bool:
    """Permanently delete an outfit history record. Returns True if a row was removed."""
    record = await session.get(OutfitHistory, uuid.UUID(history_id))
    if not record or str(record.user_id) != user_id:
        return False
    await session.delete(record)
    await session.flush()
    logger.info("outfit_history_deleted", history_id=history_id, user_id=user_id)
    return True


async def list_outfit_history(
    session: AsyncSession,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all outfit history for a user, newest first."""
    result = await session.execute(
        select(OutfitHistory)
        .where(OutfitHistory.user_id == uuid.UUID(user_id))
        .order_by(desc(OutfitHistory.created_at))
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "occasion": r.occasion,
            "weather_context": r.weather_context,
            "selected_item_ids": r.selected_item_ids or [],
            "matching_score": r.matching_score,
            "recommendation_text": r.recommendation_text,
            "improvement_tips": r.improvement_tips or [],
            "was_saved": r.was_saved,
            "was_worn": r.was_worn,
            "user_feedback": r.user_feedback,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
