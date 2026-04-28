"""Aggregate all v1 routers."""

from fastapi import APIRouter

from app.api.v1 import ai, auth, closet, social, ws

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(closet.router)
api_router.include_router(social.router)
api_router.include_router(ai.router)
api_router.include_router(ws.router)
