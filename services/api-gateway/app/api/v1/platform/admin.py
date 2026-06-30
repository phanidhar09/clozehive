"""Admin operational endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

from app.api.v1.intelligence.services.knowledge_mining_service import refresh_learned_knowledge
from app.core.deps import AdminUser, DbSession
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/backup-status")
async def backup_status(_: AdminUser):
    backup_dir = Path("./backups")
    backups = sorted(backup_dir.glob("*.sql.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not backups:
        raise NotFoundError("No database backups found.")

    latest = backups[0]
    stat = latest.stat()
    last_backup = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    age_hours = round((datetime.now(UTC) - last_backup).total_seconds() / 3600, 1)
    if age_hours > 49:
        status = "critical"
    elif age_hours > 25:
        status = "warning"
    else:
        status = "ok"

    return {
        "last_backup": last_backup.isoformat().replace("+00:00", "Z"),
        "backup_age_hours": age_hours,
        "backup_size_mb": round(stat.st_size / (1024 * 1024), 2),
        "status": status,
    }


@router.post("/knowledge/refresh-learned")
async def refresh_learned_knowledge_endpoint(_: AdminUser, session: DbSession):
    """Rebuild the community "learned" fashion-knowledge doc from current usage.

    Point a scheduler (cron / Render job / k8s CronJob) at this endpoint to keep the
    learned knowledge fresh. Returns 0 documents when there isn't enough data yet.
    The request-scoped session commits on success — no explicit commit here.
    """
    written = await refresh_learned_knowledge(session)
    return {"status": "ok", "documents_written": written}
