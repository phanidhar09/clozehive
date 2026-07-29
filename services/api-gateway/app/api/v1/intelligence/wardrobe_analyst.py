"""Wardrobe analyst agent routes — /api/v1/wardrobe-analyst/*

Endpoints:
  POST /wardrobe-analyst/ask  — ask an open-ended question about the wardrobe

Gated behind ``WARDROBE_ANALYST_AGENT_ENABLED`` (default off). Unlike the chat
endpoints this runs a tool-calling loop, so a single request can issue several
generations — the rate limit is correspondingly tighter.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.v1.intelligence.services.agents import wardrobe_analyst
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.core.rate_limit import limiter

router = APIRouter(prefix="/wardrobe-analyst", tags=["Wardrobe Analyst"])
logger = get_logger("wardrobe_analyst.routes")
settings = get_settings()


class AnalystRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


@router.post("/ask")
# Tighter than chat's 20/min: each call is a loop of up to (max_iterations + 1)
# generations, so the per-request cost is several times a normal turn.
@limiter.limit("6/minute")
async def ask_analyst(
    request: Request,
    body: AnalystRequest,
    user_id: CurrentUser,
    session: DbSession,
) -> dict[str, Any]:
    """Answer a wardrobe-level question using read-only wardrobe tools.

    The response carries ``tools_used`` and ``steps`` alongside the answer so the
    client can show what was actually consulted — the agent equivalent of the
    grounding metadata the chat paths return.
    """
    if not settings.wardrobe_analyst_agent_enabled:
        raise ServiceUnavailableError("The wardrobe analyst is not enabled in this environment.")

    return await wardrobe_analyst.analyze(session, user_id, body.question)
