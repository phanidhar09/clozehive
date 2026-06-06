"""Travel domain — trips, packing memory, weather."""

from fastapi import APIRouter

from app.api.v1.travel import packing_memory, trips, weather

router = APIRouter()
router.include_router(trips.router)
router.include_router(packing_memory.router)
router.include_router(weather.router)
