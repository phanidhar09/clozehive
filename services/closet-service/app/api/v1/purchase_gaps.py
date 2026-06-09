"""Purchase Gap Detection endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.services import purchase_gap_service

router = APIRouter(prefix="/purchase-gaps", tags=["Purchase Gaps"])


@router.get("/")
async def get_purchase_gaps(
    user_id: CurrentUser,
    session: DbSession,
    resolved: bool = Query(False, description="Include resolved gaps"),
    limit: int = Query(30, ge=1, le=100),
):
    """
    Return the user's wardrobe gaps ordered by priority score.

    Gaps are auto-detected from:
    - Missing closet categories (structural gaps)
    - Items missing from packing plans (trip gaps)
    - Missing pieces from outfit analysis (outfit gaps)
    """
    gaps = await purchase_gap_service.get_purchase_gaps(
        session, user_id, resolved=resolved, limit=limit
    )
    return {
        "count": len(gaps),
        "gaps": gaps,
    }


@router.patch("/{gap_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_purchase_gap(
    gap_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
):
    """Mark a purchase gap as resolved (e.g. item purchased or no longer needed)."""
    result = await purchase_gap_service.resolve_purchase_gap(
        session, str(gap_id), user_id
    )
    if not result:
        raise NotFoundError("Purchase gap not found")
    return result


@router.delete("/{gap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_gap(
    gap_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
):
    """Permanently delete a purchase gap from the user's list."""
    ok = await purchase_gap_service.delete_purchase_gap(
        session, str(gap_id), user_id
    )
    if not ok:
        raise NotFoundError("Purchase gap not found")
