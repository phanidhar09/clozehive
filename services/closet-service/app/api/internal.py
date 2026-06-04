"""Internal (service-to-service) endpoints — not exposed to browsers.

Protected by the shared ``INTERNAL_SERVICE_TOKEN`` (``X-Internal-Token`` header),
never by user JWTs. Mounted at ``/internal`` (outside ``/api/v1``).

``DELETE /internal/users/{user_id}`` replaces the old ON DELETE CASCADE: when
api-gateway erases a user account it calls this to purge that user's wardrobe
data from closet-service's database (and clean up their closet images).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, status
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.services.upload_service import delete_upload

router = APIRouter(prefix="/internal", tags=["internal"])
logger = get_logger("internal")
settings = get_settings()

# User-scoped tables in CHILD-FIRST delete order (respects intra-domain FKs).
# fashion_knowledge_documents is intentionally excluded — it is global, not
# per-user (no user_id column).
_PURGE_ORDER: tuple[str, ...] = (
    "outfit_feedback",     # → outfits
    "ai_chat_messages",    # → ai_chat_sessions
    "packing_memory",      # → trips, packing_plans
    "packing_plans",       # → trips
    "ai_chat_sessions",
    "daily_nudges",
    "outfit_history",
    "purchase_gaps",
    "user_style_profiles",
    "outfits",
    "closet_items",
    "trips",
)


def _verify_internal_token(x_internal_token: str | None) -> None:
    expected = settings.internal_service_token
    # Fail closed: if no token is configured, refuse rather than allow-all.
    if not expected or x_internal_token != expected:
        raise AuthenticationError("Invalid internal service token")


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def purge_user_data(
    user_id: UUID,
    session: DbSession,
    bg: BackgroundTasks,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, object]:
    """Delete all of a user's wardrobe data from closet-service. Idempotent."""
    _verify_internal_token(x_internal_token)

    # Collect closet image URLs before deletion so we can clean up storage.
    image_rows = (await session.execute(
        text(
            "SELECT image_url, original_image_url, processed_image_url "
            "FROM closet_items WHERE user_id = :uid"
        ),
        {"uid": user_id},
    )).all()
    image_urls = list({
        url for row in image_rows for url in (row[0], row[1], row[2]) if url
    })

    deleted: dict[str, int] = {}
    for table in _PURGE_ORDER:
        result = await session.execute(
            text(f'DELETE FROM "{table}" WHERE user_id = :uid'),  # noqa: S608 — table from fixed allowlist
            {"uid": user_id},
        )
        deleted[table] = result.rowcount or 0
    await session.commit()

    # Best-effort storage cleanup after the DB commit (never blocks deletion).
    for url in image_urls:
        bg.add_task(delete_upload, url)

    total = sum(deleted.values())
    logger.info("user_data_purged", user_id=str(user_id), rows=total, images=len(image_urls))
    return {"user_id": str(user_id), "deleted_rows": total, "by_table": deleted}
