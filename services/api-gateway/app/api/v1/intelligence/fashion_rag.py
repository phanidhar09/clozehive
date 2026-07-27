"""Fashion Knowledge Base RAG endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Query

from app.api.v1.intelligence.services.fashion_rag_service import search_fashion_knowledge
from app.core import langfuse_client
from app.core.deps import CurrentUser, DbSession

router = APIRouter(prefix="/fashion-knowledge", tags=["Fashion Knowledge"])


@router.get("/search")
async def search_fashion_knowledge_endpoint(
    user_id: CurrentUser,
    session: DbSession,
    query: str = Query(..., min_length=2, max_length=500, description="Fashion question or keyword"),
    limit: int = Query(5, ge=1, le=10),
    category: str | None = Query(
        None, description="Filter by category: color, occasion, seasonal, styling, travel, fit, wardrobe, weather"
    ),
):
    """
    Search the fashion knowledge base for styling advice.

    Returns relevant fashion knowledge documents ranked by semantic similarity.
    """
    started = time.perf_counter()
    docs = await search_fashion_knowledge(session, query, limit=limit, category=category)
    elapsed = time.perf_counter() - started

    # Live retrieval-quality trace (Langfuse). No-op unless Langfuse is configured.
    top_relevance = max((float(d.get("relevance_score") or d.get("score") or 0.0) for d in docs), default=0.0)
    langfuse_client.record_retrieval(
        query=query,
        doc_count=len(docs),
        top_relevance=top_relevance,
        latency_seconds=elapsed,
        user_id=user_id,
        metadata={"category": category},
    )

    return {
        "query": query,
        "count": len(docs),
        "results": docs,
    }
