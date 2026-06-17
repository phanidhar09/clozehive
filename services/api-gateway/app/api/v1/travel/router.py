"""Travel domain — weather (always on); trips + packing memory (migrated-routes gate)."""

from fastapi import APIRouter

from app.api.v1.travel import packing_memory, trips, weather
from app.core.config import get_settings

router = APIRouter()
# weather stays on the gateway (nginx routes /weather here).
router.include_router(weather.router)

# trips + packing memory (both under /trips) mount under the migrated-routes gate.
if get_settings().mount_migrated_routes:
    router.include_router(trips.router)
    router.include_router(packing_memory.router)
