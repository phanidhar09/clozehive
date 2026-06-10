"""Personalized Packing Memory RAG service.

Saves trip packing plans as memories and retrieves them to improve
future packing recommendations for similar destinations/seasons.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rag import PackingMemory
from app.core.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.rag.query_builder import build_packing_memory_query
from app.rag.rerank import rerank_packing_memories

logger = get_logger("packing_memory_service")


def _packing_context_text(
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None,
    start_date: str | None,
    end_date: str | None,
) -> str:
    """Build a searchable text description of a packing context."""
    parts = [f"Destination: {destination}", f"Purpose: {purpose}"]
    if start_date and end_date:
        parts.append(f"Dates: {start_date} to {end_date}")
    if weather_summary:
        cond = weather_summary.get("dominant_condition", "")
        avg_high = weather_summary.get("avg_high")
        avg_low = weather_summary.get("avg_low")
        rainy = weather_summary.get("rainy_days", 0)
        if cond:
            parts.append(f"Weather: {cond}")
        if avg_high is not None:
            parts.append(f"Average high {avg_high:.0f}°C")
        if rainy:
            parts.append(f"{rainy} rainy days")
    return ". ".join(parts)


async def save_packing_memory(
    session: AsyncSession,
    user_id: str,
    trip_id: str | None,
    destination: str,
    start_date: str | None,
    end_date: str | None,
    purpose: str,
    weather_summary: dict[str, Any] | None,
    packed_item_ids: list[str],
    missing_items: list[dict[str, Any]],
    saved_plan_id: str | None = None,
) -> PackingMemory | None:
    """Persist a packing plan as a memory record."""
    try:
        context_text = _packing_context_text(
            destination, purpose, weather_summary, start_date, end_date
        )
        embedding = await generate_text_embedding(context_text)

        record = PackingMemory(
            user_id=uuid.UUID(user_id),
            trip_id=uuid.UUID(trip_id) if trip_id else None,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            purpose=purpose,
            weather_summary=weather_summary,
            packed_item_ids=packed_item_ids,
            missing_items=missing_items,
            saved_plan_id=uuid.UUID(saved_plan_id) if saved_plan_id else None,
            embedding=embedding,
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        logger.info(
            "packing_memory_saved",
            user_id=user_id,
            destination=destination,
            purpose=purpose,
        )
        return record
    except Exception as exc:
        logger.warning("packing_memory_save_failed", error=str(exc), user_id=user_id)
        return None


async def search_similar_packing_memories(
    session: AsyncSession,
    user_id: str,
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Retrieve past packing memories similar to the current trip context."""
    query_text = build_packing_memory_query(
        destination, purpose, weather_summary, start_date, end_date
    )
    embedding = await generate_text_embedding(query_text)
    if not embedding:
        return []

    fetch_limit = min(max(limit * 3, limit), 15)
    rows = await pgvector_cosine_search(
        session,
        table="packing_memory",
        embedding=embedding,
        user_id=user_id,
        limit=fetch_limit,
        threshold=0.55,
    )
    records = [
        {
            "id": str(r["id"]),
            "destination": r["destination"],
            "purpose": r.get("purpose"),
            "start_date": r.get("start_date"),
            "end_date": r.get("end_date"),
            "weather_summary": r.get("weather_summary"),
            "packed_item_ids": r.get("packed_item_ids") or [],
            "missing_items": r.get("missing_items") or [],
            "user_feedback": r.get("user_feedback"),
            "similarity_score": round(float(r.get("similarity_score", 0)), 3),
            "created_at": str(r.get("created_at", "")),
        }
        for r in rows
    ]
    reranked = rerank_packing_memories(
        records, purpose=purpose, destination=destination
    )
    return reranked[:limit]


async def get_packing_memory_for_prompt(
    session: AsyncSession,
    user_id: str,
    destination: str,
    purpose: str,
    weather_summary: dict[str, Any] | None = None,
    limit: int = 3,
) -> str:
    """Return a formatted string of relevant packing memories for prompt injection."""
    memories = await search_similar_packing_memories(
        session, user_id, destination, purpose, weather_summary, limit=limit
    )
    if not memories:
        return ""
    lines = ["[Previous Packing History — similar trips]"]
    for m in memories:
        packed_count = len(m.get("packed_item_ids") or [])
        missing_names = [mi.get("name", "") for mi in (m.get("missing_items") or [])[:3]]
        missing_str = f"Missing: {', '.join(missing_names)}" if missing_names else ""
        feedback = m.get("user_feedback") or ""
        lines.append(
            f"• {m['destination']} ({m.get('purpose')}) — {packed_count} items packed"
            + (f" | {missing_str}" if missing_str else "")
            + (f" | Feedback: {feedback[:80]}" if feedback else "")
        )
    return "\n".join(lines)


async def update_packing_memory_feedback(
    session: AsyncSession,
    memory_id: str,
    user_id: str,
    feedback: str,
) -> dict[str, Any] | None:
    """Record user feedback on a past packing plan."""
    record = await session.get(PackingMemory, uuid.UUID(memory_id))
    if not record or str(record.user_id) != user_id:
        return None
    record.user_feedback = feedback
    await session.flush()
    return {"id": str(record.id), "user_feedback": record.user_feedback}


async def get_trip_packing_memory(
    session: AsyncSession,
    trip_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """Get the packing memory record for a specific trip."""
    result = await session.execute(
        select(PackingMemory).where(
            PackingMemory.trip_id == uuid.UUID(trip_id),
            PackingMemory.user_id == uuid.UUID(user_id),
        )
    )
    record = result.scalars().first()
    if not record:
        return None
    return {
        "id": str(record.id),
        "destination": record.destination,
        "purpose": record.purpose,
        "start_date": record.start_date,
        "end_date": record.end_date,
        "weather_summary": record.weather_summary,
        "packed_item_ids": record.packed_item_ids or [],
        "missing_items": record.missing_items or [],
        "user_feedback": record.user_feedback,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
