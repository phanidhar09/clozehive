"""Authenticated style profile + onboarding status."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.schemas.style_profile import (
    CompleteOnboardingBody,
    OnboardingStatusResponse,
    OnboardingSubmitBody,
    StyleProfileCreate,
    StyleProfileResponse,
    StyleProfileUpdate,
)
from app.services import style_profile_service

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("/onboarding-status", response_model=OnboardingStatusResponse)
async def onboarding_status(user_id: CurrentUser, session: DbSession):
    return await style_profile_service.get_onboarding_status(session, UUID(user_id))


@router.get("/style", response_model=StyleProfileResponse)
async def get_style_profile(user_id: CurrentUser, session: DbSession):
    data = await style_profile_service.get_style_profile(session, UUID(user_id))
    if data is None:
        raise NotFoundError("Style profile not found")
    return data


@router.post("/style", response_model=StyleProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_style_profile(
    body: StyleProfileCreate, user_id: CurrentUser, session: DbSession
):
    return await style_profile_service.create_style_profile(session, UUID(user_id), body)


@router.patch("/style", response_model=StyleProfileResponse)
async def patch_style_profile(
    body: StyleProfileUpdate, user_id: CurrentUser, session: DbSession
):
    return await style_profile_service.update_style_profile(session, UUID(user_id), body)


@router.post("/style/complete", response_model=StyleProfileResponse)
async def complete_style_onboarding(
    body: CompleteOnboardingBody, user_id: CurrentUser, session: DbSession
):
    return await style_profile_service.complete_onboarding(session, UUID(user_id), body)


@router.post("/onboarding/submit", response_model=StyleProfileResponse)
async def submit_onboarding(
    body: OnboardingSubmitBody, user_id: CurrentUser, session: DbSession
):
    """V2 onboarding wizard — saves all answers in one call and marks completion."""
    return await style_profile_service.submit_onboarding(session, UUID(user_id), body)


@router.post("/style/refresh-summary", response_model=StyleProfileResponse)
async def refresh_style_summary(user_id: CurrentUser, session: DbSession):
    """Re-generate style summary + archetype using latest wardrobe & profile data."""
    return await style_profile_service.refresh_style_summary(session, UUID(user_id))
