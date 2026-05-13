"""Business logic for user style profiles."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client
from app.models.user_style_profile import UserStyleProfile
from app.repositories.style_profile_repo import UserStyleProfileRepository
from app.schemas.style_profile import (
    CompleteOnboardingBody,
    OnboardingStatusResponse,
    StyleProfileCreate,
    StyleProfileResponse,
    StyleProfileUpdate,
)

logger = get_logger("style_profile_service")
settings = get_settings()


def _row_to_response(row: UserStyleProfile) -> StyleProfileResponse:
    return StyleProfileResponse.from_orm_row(row)


def _extract_profile_data(row: UserStyleProfile) -> dict:
    return {
        "user_id": str(row.user_id),
        "gender": row.custom_gender if row.gender == "custom" and row.custom_gender else row.gender,
        "age_range": row.age_range,
        "height": f"{row.height_value} {row.height_unit}" if row.height_value and row.height_unit else None,
        "weight": f"{row.weight_value} {row.weight_unit}" if row.weight_value and row.weight_unit else None,
        "body_types": row.body_types or [],
        "custom_body_type": row.custom_body_type,
        "fit_preferences": row.fit_preferences or [],
        "custom_fit_notes": row.custom_fit_notes,
        "size_profile": row.size_profile or {},
        "style_preferences": row.style_preferences or [],
        "favorite_colors": row.favorite_colors or [],
        "avoided_colors": row.avoided_colors or [],
        "neutral_color_preference": row.neutral_color_preference,
        "bold_color_preference": row.bold_color_preference,
        "occasion_preferences": row.occasion_preferences or [],
        "climate_preferences": row.climate_preferences or [],
    }


async def _background_generate_style_summary(user_id: UUID, profile_data: dict) -> None:
    """Run in its own DB session so it never blocks an HTTP response."""
    if not settings.openai_api_key:
        return
    from app.db.session import AsyncSessionLocal
    from app.repositories.style_profile_repo import UserStyleProfileRepository
    non_empty = {k: v for k, v in profile_data.items() if k != "user_id" and v not in (None, [], {}, "")}
    if not non_empty:
        return
    prompt = (
        "You are a personal stylist assistant. Based on the following user style profile data, "
        "write a concise 2-3 sentence natural-language summary of this person's style identity, "
        "body preferences, and dressing needs. The summary will be used as context for an AI "
        "fashion assistant. Be specific and helpful — mention body type, fit preferences, color "
        "palette, occasions they dress for, and climate needs.\n\n"
        f"Profile:\n{json.dumps(non_empty, indent=2)}"
    )
    try:
        client = make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        summary = (completion.choices[0].message.content or "").strip()
        if not summary:
            return
        async with AsyncSessionLocal() as session:
            repo = UserStyleProfileRepository(session)
            row = await repo.get_by_user_id(user_id)
            if row:
                row.style_summary = summary
                session.add(row)
                await session.commit()
                logger.info("style_summary_generated", user_id=str(user_id), chars=len(summary))
    except Exception as exc:
        logger.warning("style_summary_generation_failed", user_id=str(user_id), error=str(exc))


def _schedule_style_summary(row: UserStyleProfile) -> None:
    """Fire-and-forget: schedule summary generation without blocking the caller."""
    profile_data = _extract_profile_data(row)
    asyncio.create_task(_background_generate_style_summary(row.user_id, profile_data))


async def get_onboarding_status(session: AsyncSession, user_id: UUID) -> OnboardingStatusResponse:
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if row is None:
        # Legacy users (no row) are not forced through onboarding.
        return OnboardingStatusResponse(
            onboarding_completed=True,
            onboarding_skipped=False,
            has_profile_record=False,
        )
    return OnboardingStatusResponse(
        onboarding_completed=row.onboarding_completed,
        onboarding_skipped=row.onboarding_skipped,
        has_profile_record=True,
    )


async def get_style_profile(session: AsyncSession, user_id: UUID) -> StyleProfileResponse | None:
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if row is None:
        return None
    return _row_to_response(row)


def _create_payload_from_schema(data: StyleProfileCreate) -> dict:
    def dec(v):
        return float(v) if v is not None else None

    return {
        "gender": data.gender,
        "custom_gender": data.custom_gender,
        "height_value": dec(data.height_value),
        "height_unit": data.height_unit,
        "weight_value": dec(data.weight_value),
        "weight_unit": data.weight_unit,
        "age_range": data.age_range,
        "body_types": data.body_types,
        "custom_body_type": data.custom_body_type,
        "fit_preferences": data.fit_preferences,
        "custom_fit_notes": data.custom_fit_notes,
        "size_profile": data.size_profile,
        "custom_size_notes": data.custom_size_notes,
        "style_preferences": data.style_preferences,
        "favorite_colors": data.favorite_colors,
        "avoided_colors": data.avoided_colors,
        "neutral_color_preference": data.neutral_color_preference,
        "bold_color_preference": data.bold_color_preference,
        "occasion_preferences": data.occasion_preferences,
        "climate_preferences": data.climate_preferences,
    }


def _apply_update(row: UserStyleProfile, data: StyleProfileUpdate) -> None:
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if k in {"height_value", "weight_value"} and v is not None:
            v = float(v)
        setattr(row, k, v)


async def create_style_profile(session: AsyncSession, user_id: UUID, payload: StyleProfileCreate) -> StyleProfileResponse:
    repo = UserStyleProfileRepository(session)
    if await repo.get_by_user_id(user_id):
        raise ConflictError("Style profile already exists — use PATCH to update")
    row = await repo.create(
        id=uuid4(),
        user_id=user_id,
        onboarding_completed=False,
        onboarding_skipped=False,
        **_create_payload_from_schema(payload),
    )
    logger.info("style_profile_created", user_id=str(user_id))
    _schedule_style_summary(row)
    return _row_to_response(row)


async def create_default_profile_row(session: AsyncSession, user_id: UUID) -> UserStyleProfile:
    """Called after signup / new OAuth user — incomplete onboarding."""
    repo = UserStyleProfileRepository(session)
    existing = await repo.get_by_user_id(user_id)
    if existing:
        return existing
    row = await repo.create(
        id=uuid4(),
        user_id=user_id,
        onboarding_completed=False,
        onboarding_skipped=False,
    )
    logger.info("style_profile_placeholder_created", user_id=str(user_id))
    return row


async def update_style_profile(session: AsyncSession, user_id: UUID, payload: StyleProfileUpdate) -> StyleProfileResponse:
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if not row:
        base = StyleProfileCreate.model_validate(
            {**StyleProfileCreate().model_dump(), **payload.model_dump(exclude_unset=True)}
        )
        return await create_style_profile(session, user_id, base)
    _apply_update(row, payload)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info("style_profile_updated", user_id=str(user_id))
    _schedule_style_summary(row)
    return _row_to_response(row)


async def complete_onboarding(
    session: AsyncSession, user_id: UUID, body: CompleteOnboardingBody
) -> StyleProfileResponse:
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if not row:
        row = await create_default_profile_row(session, user_id)
    row.onboarding_completed = True
    row.onboarding_skipped = body.skipped
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info(
        "style_onboarding_completed",
        user_id=str(user_id),
        skipped=body.skipped,
    )
    if not body.skipped:
        _schedule_style_summary(row)
    return _row_to_response(row)
