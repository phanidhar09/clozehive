"""Closet item vector similarity helpers for vision-service."""

from __future__ import annotations

from uuid import UUID

from langsmith import traceable
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client
from app.db.session import AsyncSessionLocal
from app.models.closet import ClosetItem

settings = get_settings()
logger = get_logger("similarity_service")

_emb_client: AsyncOpenAI | None = None


def _embedding_client() -> AsyncOpenAI:
    global _emb_client
    if _emb_client is None:
        _emb_client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        )
    return _emb_client


def _item_to_text(item: ClosetItem) -> str:
    """Build a rich embedding string — mirrors closet-service item_to_embedding_text()
    so both services produce vectors in the same semantic space."""
    parts: list[str] = []
    item_type = getattr(item, "subcategory", None) or item.category or "item"
    descriptor = " ".join(p for p in [item.color or "", item_type] if p)
    if item.name and item.name.lower() != item_type.lower():
        descriptor = f"{descriptor} called '{item.name}'"
    if descriptor.strip():
        parts.append(descriptor)
    notes = getattr(item, "notes", None) or getattr(item, "description", None)
    if notes:
        parts.append(str(notes))
    if getattr(item, "brand", None):
        parts.append(f"Brand: {item.brand}")
    fabric = getattr(item, "fabric", None) or getattr(item, "material", None)
    pattern = getattr(item, "pattern", None)
    if pattern and pattern.lower() not in ("solid", "unknown", ""):
        parts.append(f"Pattern: {pattern}")
    season = getattr(item, "season", None) or []
    if season:
        parts.append(f"Suitable for {', '.join(season)}")
    occasion = getattr(item, "occasion", None) or []
    if occasion:
        parts.append(f"Worn for {', '.join(occasion)}")
    tags = item.tags or []
    if tags:
        parts.append(f"Style: {', '.join(tags)}")
    tail = [p for p in [item.category or "", item.color or "", fabric or ""] if p]
    if tail:
        parts.append(" · ".join(tail))
    return ". ".join(p for p in parts if p.strip()) + "."


@traceable(name="vision_openai_embedding", run_type="embedding")
async def generate_item_embedding(item: ClosetItem) -> list[float]:
    description = _item_to_text(item)
    if not settings.openai_api_key:
        logger.warning("embedding_fallback", reason="OPENAI_API_KEY not set", item_id=str(item.id))
        return [0.0] * 1536
    response = await _embedding_client().embeddings.create(
        model=settings.embedding_model,
        input=description,
        timeout=20.0,
    )
    vector = response.data[0].embedding
    if len(vector) != 1536:
        raise ValueError(f"Embedding model returned {len(vector)} dimensions; expected 1536")
    return [float(v) for v in vector]


async def update_item_embedding_job(item_id: str) -> None:
    """
    Background-safe embedding update: opens its own session and commits.
    """
    async with AsyncSessionLocal() as session:
        try:
            item = await session.get(ClosetItem, UUID(item_id))
            if item is None:
                return
            item.embedding = await generate_item_embedding(item)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
