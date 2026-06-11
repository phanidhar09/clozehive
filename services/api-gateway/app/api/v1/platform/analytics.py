"""
Analytics routes — /api/v1/analytics/*
MVP: Closet insights and analytics
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.platform.schemas.analytics import ClosetAnalyticsResponse
from app.api.v1.platform.services.analytics_service import AnalyticsService
from app.core.deps import CurrentUser
from app.db.session import get_session

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_svc(session: AsyncSession) -> AnalyticsService:
    return AnalyticsService(session)


# ── Closet Analytics ──────────────────────────────────────────────────────────


@router.get("/closet", response_model=ClosetAnalyticsResponse)
async def get_closet_analytics(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.get_closet_analytics(UUID(user_id))
