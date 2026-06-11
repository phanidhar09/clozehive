"""Weather routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.travel.services import weather_service
from app.core import cache_service
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import ForbiddenError, NotFoundError

router = APIRouter(prefix="/weather", tags=["Weather"])
settings = get_settings()


@router.get("/current")
async def current_weather(user_id: CurrentUser, session: DbSession):
    user = await UserRepository(session).get(UUID(user_id))
    permissions = user.permissions if user else None
    if not isinstance(permissions, dict) or not permissions.get("location"):
        raise ForbiddenError("Location permission is required for weather.")

    coords = permissions.get("location_coords")
    label = permissions.get("location_label")
    has_coords = isinstance(coords, dict) and coords.get("lat") is not None and coords.get("lon") is not None
    if not has_coords and not label:
        raise NotFoundError("No location is stored for this user.")

    # Cache the upstream forecast (shared by all users at the same place) with
    # single-flight so a burst doesn't fan out to OpenWeather, SWR so an expired
    # entry is served while refreshing, and negative caching to absorb failures.
    if has_coords:
        assert isinstance(coords, dict)
        key = cache_service.namespaced_key("weather", "coords", f"{coords['lat']:.3f},{coords['lon']:.3f}")

        async def _compute():
            return await weather_service.get_current_weather(float(coords["lat"]), float(coords["lon"]), label)
    else:
        key = cache_service.namespaced_key("weather", "city", str(label).lower())

        async def _compute():
            return await weather_service.get_weather_by_city(str(label))

    result = await cache_service.get_or_compute(
        key,
        settings.cache_ttl_weather,
        _compute,
        swr_seconds=600,
        negative_ttl=60,
    )
    if result is None:
        raise NotFoundError("Weather is temporarily unavailable for this location.")
    return result
