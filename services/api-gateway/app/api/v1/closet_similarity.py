"""Closet similarity search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, UploadFile, File
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.services import closet_similarity_service
from app.services.embedding_service import item_to_embedding_text

router = APIRouter(prefix="/closet", tags=["Closet Similarity"])


class SimilarByItemRequest(BaseModel):
    closet_item_id: str
    limit: int = 5


class SimilarByTextRequest(BaseModel):
    query: str
    limit: int = 5


class SimilarByImageUrlRequest(BaseModel):
    image_url: str
    limit: int = 5


@router.post("/similar")
async def find_similar_closet_items(
    user_id: CurrentUser,
    session: DbSession,
    closet_item_id: str | None = Query(None, description="Find items similar to this closet item"),
    query: str | None = Query(None, description="Text description to search by (e.g. 'blue casual shirt')"),
    image_url: str | None = Query(None, description="Image URL to find visually similar items"),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Find similar items in the user's closet.

    Accepts one of:
    - closet_item_id  — find items similar to an existing item
    - query           — find items matching a text description
    - image_url       — find visually similar items (text-fallback in MVP)

    Returns ranked results with similarity scores and explanations.
    """
    if closet_item_id:
        results = await closet_similarity_service.find_similar_by_item_id(
            session, closet_item_id, user_id, limit=limit
        )
        query_type = "closet_item"
        query_ref = closet_item_id
    elif query:
        results = await closet_similarity_service.find_similar_by_text(
            session, query, user_id, limit=limit
        )
        query_type = "text_query"
        query_ref = query
    elif image_url:
        results = await closet_similarity_service.find_similar_by_image_url(
            session, image_url, user_id, limit=limit
        )
        query_type = "image_url"
        query_ref = image_url
    else:
        return {
            "query_type": "none",
            "message": "Provide one of: closet_item_id, query, or image_url",
            "results": [],
        }

    return {
        "query_type": query_type,
        "query_ref": query_ref,
        "count": len(results),
        "results": results,
    }


@router.get("/similar/{item_id}")
async def get_similar_to_item(
    item_id: str,
    user_id: CurrentUser,
    session: DbSession,
    limit: int = Query(5, ge=1, le=20),
):
    """Convenience GET endpoint: find items similar to a specific closet item."""
    results = await closet_similarity_service.find_similar_by_item_id(
        session, item_id, user_id, limit=limit
    )
    return {
        "query_type": "closet_item",
        "item_id": item_id,
        "count": len(results),
        "results": results,
    }
