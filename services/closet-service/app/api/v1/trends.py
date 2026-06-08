"""Fashion trend ingestion endpoints (admin-triggered).

A manual refresh seam so trends can be pulled on demand (and tested) without
waiting on a scheduled job. Wire a cron/scheduler to ``refresh_trends_for_regions``
for automatic weekly updates.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import AdminUser, DbSession
from app.services.trend_ingest_service import refresh_trends_for_regions

router = APIRouter(prefix="/trends", tags=["Trends"])


class TrendRefreshRequest(BaseModel):
    # Omit to refresh the full curated destination set from location_intel_service.
    regions: list[str] | None = Field(
        None,
        description="Specific regions to refresh (e.g. ['dubai', 'tokyo']). "
        "Defaults to all curated destinations.",
    )


@router.post("/refresh")
async def refresh_trends(
    body: TrendRefreshRequest,
    admin_id: AdminUser,
    session: DbSession,
):
    """Pull live fashion trends per region and upsert them into the RAG knowledge base.

    Admin-only. Returns which regions were refreshed vs. skipped (e.g. when the
    upstream trend source rate-limited or returned no rising queries).
    """
    return await refresh_trends_for_regions(session, regions=body.regions)
