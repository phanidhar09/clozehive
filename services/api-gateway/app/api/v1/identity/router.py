"""Identity domain — authentication and user profile."""

from fastapi import APIRouter

from app.api.v1.identity import auth, profile

router = APIRouter()
router.include_router(auth.router)
router.include_router(profile.router)
