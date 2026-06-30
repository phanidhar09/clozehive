"""Fashion Knowledge Base RAG service.

Manages a seeded corpus of fashion documents. On first request it lazily
seeds the table (idempotent — skips if already populated). Documents are
embedded with OpenAI and searched with pgvector cosine similarity.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.core.logging import get_logger
from app.models.rag import FashionKnowledgeDocument
from app.rag.knowledge_loader import load_seed_documents
from app.rag.query_builder import (
    build_fashion_knowledge_query,
    extract_keywords,
    infer_query_signals,
)
from app.rag.rerank import rerank_fashion_documents

logger = get_logger("fashion_rag_service")

# ── Seed corpus ───────────────────────────────────────────────────────────────

# Loaded from versioned YAML data files in app/rag/knowledge/ (see knowledge_loader).
# Add/extend knowledge there — no code change needed. taxonomy.yaml lists what to grow next.
_KNOWLEDGE_SEED: list[dict[str, Any]] = load_seed_documents()


# Filterable metadata persisted alongside the keyword tags inside the JSONB column.
_TAGS_META_KEYS = ("gender", "formality_level", "region", "source")


def _build_tags_payload(doc: dict[str, Any]) -> dict[str, Any]:
    """Pack keyword tags + filterable metadata into the FashionKnowledgeDocument.tags JSONB."""
    payload: dict[str, Any] = {"tags": doc.get("tags", [])}
    for key in _TAGS_META_KEYS:
        if doc.get(key) is not None:
            payload[key] = doc[key]
    return payload


# ── Service functions ─────────────────────────────────────────────────────────


async def ensure_seeded(session: AsyncSession) -> None:
    """Seed missing fashion knowledge documents. Idempotent — only inserts missing titles."""
    existing_titles_result = await session.execute(select(FashionKnowledgeDocument.title))
    existing_titles = {row[0] for row in existing_titles_result.all()}

    missing = [doc for doc in _KNOWLEDGE_SEED if doc["title"] not in existing_titles]
    if not missing:
        return

    logger.info("fashion_kb_seeding", new_docs=len(missing), total_seed=len(_KNOWLEDGE_SEED))
    for doc in missing:
        content_for_embedding = f"Title: {doc['title']}. {doc['content']}"
        embedding = await generate_text_embedding(content_for_embedding)
        db_doc = FashionKnowledgeDocument(
            title=doc["title"],
            content=doc["content"],
            category=doc["category"],
            season=doc.get("season"),
            occasion=doc.get("occasion"),
            tags=_build_tags_payload(doc),
            embedding=embedding,
        )
        session.add(db_doc)
    logger.info("fashion_kb_seeded", added=len(missing))


async def search_fashion_knowledge(
    session: AsyncSession,
    query: str,
    limit: int = _DEFAULT_LIMIT,
    category: str | None = None,
    occasion: str | None = None,
    weather: str = "",
) -> list[dict[str, Any]]:
    """Retrieve relevant fashion knowledge documents for a query."""
    await ensure_seeded(session)

    inferred = infer_query_signals(query)
    effective_occasion = occasion or inferred.get("occasion")
    effective_season = inferred.get("season")
    effective_weather = weather or inferred.get("weather") or ""

    enriched_query = build_fashion_knowledge_query(
        query,
        occasion=effective_occasion,
        weather=effective_weather,
        category=category,
    )

    docs: list[dict[str, Any]] = []
    embedding = await generate_text_embedding(enriched_query)
    if embedding:
        fetch_limit = min(max(limit * 3, limit), 15)
        rows = await pgvector_cosine_search(
            session,
            table="fashion_knowledge_documents",
            embedding=embedding,
            user_id=None,
            limit=fetch_limit,
            threshold=0.55,
            filter_category=category,
        )
        docs = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "content": r["content"],
                "category": r["category"],
                "season": r.get("season"),
                "occasion": r.get("occasion"),
                "relevance_score": round(float(r.get("similarity_score", 0)), 3),
            }
            for r in rows
        ]

    if not docs:
        docs = await _keyword_fallback(session, enriched_query, category, limit)

    reranked = rerank_fashion_documents(
        docs,
        occasion=effective_occasion,
        season=effective_season,
        weather=effective_weather or None,
    )
    return reranked[:limit]


async def _keyword_fallback(
    session: AsyncSession,
    query: str,
    category: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Keyword search when embeddings are unavailable or vector search is empty."""
    keywords = extract_keywords(query)
    if not keywords:
        return []

    conditions = []
    for kw in keywords:
        pattern = f"%{kw}%"
        conditions.extend(
            [
                FashionKnowledgeDocument.title.ilike(pattern),
                FashionKnowledgeDocument.content.ilike(pattern),
                FashionKnowledgeDocument.occasion.ilike(pattern),
                FashionKnowledgeDocument.season.ilike(pattern),
            ]
        )

    stmt = select(FashionKnowledgeDocument).where(or_(*conditions))
    if category:
        stmt = stmt.where(FashionKnowledgeDocument.category == category)
    stmt = stmt.limit(limit)

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    except Exception as exc:
        logger.warning("fashion_kb_keyword_fallback_failed", error=str(exc))
        return []

    return [
        {
            "id": str(doc.id),
            "title": doc.title,
            "content": doc.content,
            "category": doc.category,
            "season": doc.season,
            "occasion": doc.occasion,
            "relevance_score": 0.50,
        }
        for doc in rows
    ]


async def get_fashion_context_for_prompt(
    session: AsyncSession,
    query: str,
    limit: int = 5,
    occasion: str | None = None,
    weather: str = "",
) -> str:
    """Return a formatted string of relevant fashion knowledge for LLM prompt injection."""
    docs = await search_fashion_knowledge(session, query, limit=limit, occasion=occasion, weather=weather)
    if not docs:
        return ""
    lines = ["[Fashion Knowledge Context]"]
    for i, doc in enumerate(docs, 1):
        # Use up to 600 chars per document for richer grounding context
        excerpt = doc["content"] if len(doc["content"]) <= 600 else doc["content"][:600] + "…"
        lines.append(f"[SOURCE-{i}] {doc['title']} (relevance: {doc['relevance_score']:.2f})\n{excerpt}")
    return "\n\n".join(lines)
