"""Admin operational endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

from app.core.deps import AdminUser
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
