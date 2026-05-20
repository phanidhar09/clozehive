"""Fashion Knowledge Base RAG endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.services.fashion_rag_service import search_fashion_knowledge

router = APIRouter(prefix="/fashion-knowledge", tags=["Fashion Knowledge"])


@router.get("/search")
async def search_fashion_knowledge_endpoint(
    user_id: CurrentUser,
    session: DbSession,
    query: str = Query(..., min_length=2, max_length=500, description="Fashion question or keyword"),
    limit: int = Query(5, ge=1, le=10),
    category: str | None = Query(None, description="Filter by category: color, occasion, seasonal, styling, travel, fit, wardrobe, weather"),
):
    """
    Search the fashion knowledge base for styling advice.

    Returns relevant fashion knowledge documents ranked by semantic similarity.
    """
    docs = await search_fashion_knowledge(session, query, limit=limit, category=category)
    return {
        "query": query,
        "count": len(docs),
        "results": docs,
    }
