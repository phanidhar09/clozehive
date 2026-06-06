"""Real User Monitoring (RUM) ingestion — browser Web Vitals → Prometheus.

The frontend (see frontend/src/observability.ts) beacons Core Web Vitals here.
Values are recorded as Prometheus metrics with bounded labels (validated in
``record_web_vital``) so this public, unauthenticated endpoint can't be used to
blow up metric cardinality. Rate-limited to blunt abuse.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.core.metrics import record_web_vital
from app.core.rate_limit import limiter

router = APIRouter(prefix="/rum", tags=["RUM"])


class WebVital(BaseModel):
    metric: str = Field(..., max_length=8)   # LCP | INP | CLS | FCP | TTFB
    value: float = Field(..., ge=0, le=600000)
    rating: str = Field(..., max_length=20)  # good | needs-improvement | poor


@router.post("/vitals", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def report_vital(request: Request, body: WebVital) -> None:
    """Record one Web Vital sample. Silently ignores invalid metric/rating."""
    record_web_vital(body.metric, body.value, body.rating)
