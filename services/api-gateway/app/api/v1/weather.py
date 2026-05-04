"""Weather routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.user_repo import UserRepository
from app.services import weather_service

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/current")
async def current_weather(user_id: CurrentUser, session: DbSession):
    user = await UserRepository(session).get(UUID(user_id))
    permissions = user.permissions if user else None
    if not isinstance(permissions, dict) or not permissions.get("location"):
        raise ForbiddenError("Location permission is required for weather.")

    coords = permissions.get("location_coords")
    label = permissions.get("location_label")
    if isinstance(coords, dict) and coords.get("lat") is not None and coords.get("lon") is not None:
        return await weather_service.get_current_weather(float(coords["lat"]), float(coords["lon"]), label)
    if label:
        return await weather_service.get_weather_by_city(str(label))
    raise NotFoundError("No location is stored for this user.")
