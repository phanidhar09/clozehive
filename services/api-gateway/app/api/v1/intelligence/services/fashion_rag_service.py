"""Fashion Knowledge Base RAG service.

Manages a seeded corpus of fashion documents. On first request it lazily
seeds the table (idempotent — skips if already populated). Documents are
embedded with OpenAI and searched with pgvector cosine similarity.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.core.logging import get_logger
from app.models.rag import FashionKnowledgeDocument
from app.rag import cross_encoder
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.knowledge_loader import load_seed_documents
from app.rag.lexical import build_lexical_index
from app.rag.metadata_filter import canonical_gender, filter_by_gender, gender_of_row
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

# BM25 index over the same corpus — the lexical half of hybrid retrieval. Built
# once at import (cheap for a small static corpus). Titles align with the seeded
# DB rows, so vector and lexical hits fuse cleanly on normalised title.
_LEXICAL_INDEX = build_lexical_index(_KNOWLEDGE_SEED)


def _title_key(doc: dict[str, Any]) -> str:
    """Normalised title — the fusion identity shared by vector and lexical hits."""
    return re.sub(r"\s+", " ", str(doc.get("title", "")).lower().strip())


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
    """Reconcile the fashion knowledge corpus to the versioned YAML source of truth.

    Idempotent and cheap at steady state (one SELECT, no writes):
      - missing titles are inserted;
      - a curated doc whose content/metadata changed in the corpus is refreshed in
        place and re-embedded — so atomic-authoring edits actually reach an
        already-seeded database, which a title-only insert never did.

    Only titles present in ``_KNOWLEDGE_SEED`` are ever read or written, so
    learned/``user_data`` documents (mined from user activity, never in the seed)
    are left completely untouched.
    """
    seed_titles = [doc["title"] for doc in _KNOWLEDGE_SEED]
    existing_result = await session.execute(
        select(FashionKnowledgeDocument).where(FashionKnowledgeDocument.title.in_(seed_titles))
    )
    existing_by_title = {row.title: row for row in existing_result.scalars().all()}

    inserted = 0
    refreshed = 0
    for doc in _KNOWLEDGE_SEED:
        tags = _build_tags_payload(doc)
        row = existing_by_title.get(doc["title"])
        if row is not None:
            # Refresh in place only when the corpus actually diverged from the DB, so
            # a steady-state re-run stays a no-op and never re-embeds needlessly.
            if (
                row.content == doc["content"]
                and row.tags == tags
                and row.category == doc["category"]
                and row.season == doc.get("season")
                and row.occasion == doc.get("occasion")
            ):
                continue
            row.content = doc["content"]
            row.category = doc["category"]
            row.season = doc.get("season")
            row.occasion = doc.get("occasion")
            row.tags = tags
            row.embedding = await generate_text_embedding(f"Title: {doc['title']}. {doc['content']}")
            refreshed += 1
            continue
        session.add(
            FashionKnowledgeDocument(
                title=doc["title"],
                content=doc["content"],
                category=doc["category"],
                season=doc.get("season"),
                occasion=doc.get("occasion"),
                tags=tags,
                embedding=await generate_text_embedding(f"Title: {doc['title']}. {doc['content']}"),
            )
        )
        inserted += 1

    if inserted or refreshed:
        logger.info("fashion_kb_seeded", inserted=inserted, refreshed=refreshed, total_seed=len(_KNOWLEDGE_SEED))


async def search_fashion_knowledge(
    session: AsyncSession,
    query: str,
    limit: int = _DEFAULT_LIMIT,
    category: str | None = None,
    occasion: str | None = None,
    weather: str = "",
    gender: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant fashion knowledge documents for a query.

    ``gender`` is an optional audience signal (typically the user's style-profile
    gender). When it resolves to a canonical ``men``/``women`` and the metadata
    pre-filter is enabled, wrong-audience documents are dropped from *both* halves
    of hybrid retrieval before ranking; ``unisex`` / untagged docs always pass.
    """
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

    settings = get_settings()
    # Audience pre-filter target — None (no filtering) unless enabled AND we have a
    # confident binary signal that maps onto the corpus's men/women partition.
    target_gender = canonical_gender(gender) if settings.rag_metadata_prefilter_enabled else None
    # Over-fetch a wider pool when pre-filtering, since dropping the wrong audience
    # shrinks the candidate list before it reaches fusion/rerank.
    fetch_cap = 20 if target_gender else 15
    fetch_limit = min(max(limit * (4 if target_gender else 3), limit), fetch_cap)

    # Dense vector half (semantic matches). ``tags_gender`` pre-filters at the SQL
    # level so the ANN order/limit runs on the audience-filtered rows.
    vector_docs: list[dict[str, Any]] = []
    embedding = await generate_text_embedding(enriched_query)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="fashion_knowledge_documents",
            embedding=embedding,
            user_id=None,
            limit=fetch_limit,
            threshold=0.55,
            filter_category=category,
            tags_gender=target_gender,
        )
        vector_docs = [
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

    if settings.rag_hybrid_enabled:
        # Lexical half (exact-term matches). Scored on the raw query — the
        # enriched query's prose scaffolding ("Styling context: …") only adds
        # low-signal tokens to BM25.
        lexical_docs = _LEXICAL_INDEX.search(query, limit=fetch_limit, category=category)
        # Mirror the dense half's SQL pre-filter on the lexical candidate pool so
        # both halves are audience-consistent before fusion.
        lexical_docs = filter_by_gender(lexical_docs, target_gender, gender_of=gender_of_row)
        docs = _fuse_hybrid(vector_docs, lexical_docs, k=settings.rag_rrf_k)
    else:
        docs = vector_docs

    if not docs:
        docs = await _keyword_fallback(session, enriched_query, category, limit)

    reranked = rerank_fashion_documents(
        docs,
        occasion=effective_occasion,
        season=effective_season,
        weather=effective_weather or None,
    )

    # Precision stage: LLM cross-encoder joint scoring over the top candidates.
    # No-op unless rag_cross_encoder_enabled; degrades to `reranked` on any failure.
    if cross_encoder.is_enabled():
        reranked = await cross_encoder.rerank(query, reranked, text_of=_doc_rerank_text)

    return reranked[:limit]


def _doc_rerank_text(doc: dict[str, Any]) -> str:
    """Passage text handed to the cross-encoder — title plus a content excerpt."""
    return f"{doc.get('title', '')}. {doc.get('content', '')}"


def _fuse_hybrid(
    vector_docs: list[dict[str, Any]],
    lexical_docs: list[dict[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    """Fuse the vector and lexical result lists with Reciprocal Rank Fusion.

    Documents are merged on normalised title, preferring the vector row (it
    carries the real DB id and the cosine relevance). ``relevance_score`` is
    overwritten with the fused score normalised to [0, 1] so the downstream
    metadata rerank (which adds absolute boosts on top) operates on a sensible
    base and the hybrid ordering survives.
    """
    if not vector_docs and not lexical_docs:
        return []

    merged: dict[str, dict[str, Any]] = {}
    for doc in lexical_docs:  # seed with lexical first so vector overwrites
        merged[_title_key(doc)] = dict(doc)
    for doc in vector_docs:
        key = _title_key(doc)
        base = merged.get(key, {})
        merged[key] = {**base, **doc, "id": doc.get("id") or base.get("id") or ""}

    fused = reciprocal_rank_fusion([vector_docs, lexical_docs], key=_title_key, k=k)
    if not fused:
        return []
    top_score = fused[0][1] or 1.0

    out: list[dict[str, Any]] = []
    for key, score in fused:
        merged_doc = merged.get(key)
        if merged_doc is None:
            continue
        clean = {k2: v for k2, v in merged_doc.items() if k2 != "lexical_score"}
        clean["relevance_score"] = round(score / top_score, 3)
        out.append(clean)
    return out


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
        # exc_info: this execute autoflushes any pending rows (e.g. a lazy KB
        # seed), so failures here can originate far away — keep the traceback.
        logger.warning("fashion_kb_keyword_fallback_failed", error=str(exc), exc_info=True)
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
    gender: str | None = None,
    user_id: Any | None = None,
) -> str:
    """Return a formatted string of relevant fashion knowledge for LLM prompt injection.

    Pass ``gender`` when the caller already has the user's audience; otherwise pass
    ``user_id`` and it is resolved from the style profile (best-effort) so the
    fashion-KB metadata pre-filter can drop wrong-audience passages. ``gender`` wins
    if both are given; neither leaves retrieval audience-neutral.
    """
    if gender is None and user_id is not None:
        from app.api.v1.identity.services.style_profile_context import load_profile_gender

        gender = await load_profile_gender(session, user_id)
    docs = await search_fashion_knowledge(
        session, query, limit=limit, occasion=occasion, weather=weather, gender=gender
    )
    if not docs:
        return ""
    lines = ["[Fashion Knowledge Context]"]
    for i, doc in enumerate(docs, 1):
        # Use up to 600 chars per document for richer grounding context
        excerpt = doc["content"] if len(doc["content"]) <= 600 else doc["content"][:600] + "…"
        lines.append(f"[SOURCE-{i}] {doc['title']} (relevance: {doc['relevance_score']:.2f})\n{excerpt}")
    return "\n\n".join(lines)
