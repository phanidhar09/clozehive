"""
Aggregate all v1 routers into a single APIRouter.
"""
from fastapi import APIRouter

from app.api.v1 import auth, users, social, groups, ai, closet

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(social.router)
api_router.include_router(groups.router)
api_router.include_router(ai.router)
api_router.include_router(closet.router)
