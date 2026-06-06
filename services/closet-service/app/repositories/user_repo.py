"""User lookup seam — closet-service does NOT own the users table.

The ``users`` table lives in the api-gateway DB. The hot path never needs it
(the JWT carries ``user_id``), but a few styling features read legacy profile
fields (``body_profile``, ``style_profile``, ``preferences``, ``permissions``)
off the user record. Those are fetched over the internal API:

    GET {gateway_internal_url}/internal/users/{id}   (X-Internal-Token: …)

This endpoint is added to api-gateway in Phase 4. Until then — or on any
failure — ``get()`` returns ``None``; every caller already guards on a missing
user, so styling degrades gracefully (no legacy-profile enrichment) while the
closet-service-owned ``user_style_profiles`` data keeps working fully.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("user_repo_seam")
settings = get_settings()


@dataclass
class RemoteUser:
    """Lightweight stand-in for the gateway's User ORM row (read-only)."""

    id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[dict[str, Any]] = None
    body_profile: Optional[dict[str, Any]] = None
    style_profile: Optional[dict[str, Any]] = None
    preferences: Optional[dict[str, Any]] = None


class UserRepository:
    """Drop-in for the gateway repo's ``.get(user_id)`` used by styling code.

    The ``session`` argument is accepted for call-site compatibility but unused —
    user data comes from the gateway, not closet-service's DB.
    """

    def __init__(self, session: Any = None) -> None:
        self._session = session

    async def get(self, user_id: UUID | str) -> Optional[RemoteUser]:
        base = (settings.gateway_internal_url or "").rstrip("/")
        if not base:
            return None
        if not settings.internal_service_token:
            # Token not configured — skip the call rather than sending an empty
            # header that would be rejected with a misleading 401 from the gateway.
            logger.debug("internal_user_lookup_skipped_no_token", user_id=str(user_id))
            return None
        url = f"{base}/internal/users/{user_id}"
        headers = {"X-Internal-Token": settings.internal_service_token}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.debug("internal_user_lookup_non_200", status=resp.status_code, user_id=str(user_id))
                return None
            data = resp.json()
            return RemoteUser(
                id=data.get("id"),
                email=data.get("email"),
                name=data.get("name"),
                role=data.get("role"),
                permissions=data.get("permissions"),
                body_profile=data.get("body_profile"),
                style_profile=data.get("style_profile"),
                preferences=data.get("preferences"),
            )
        except Exception as exc:  # noqa: BLE001 — never break styling on a lookup miss
            logger.debug("internal_user_lookup_failed", error=str(exc), user_id=str(user_id))
            return None
