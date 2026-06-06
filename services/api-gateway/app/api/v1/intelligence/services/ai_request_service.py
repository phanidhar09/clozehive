"""Persistence helpers for asynchronous AI request lifecycle."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    user_id: UUID,
    request_type: str,
    input_payload: dict[str, Any],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ai_requests (id, user_id, request_type, status, input_payload)
            VALUES (:id, :user_id, :request_type, 'accepted', CAST(:input_payload AS jsonb))
            """
        ),
        {
            "id": request_id,
            "user_id": user_id,
            "request_type": request_type,
            "input_payload": __import__("json").dumps(input_payload, default=str),
        },
    )
