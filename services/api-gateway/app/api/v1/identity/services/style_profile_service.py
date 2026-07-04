"""Business logic for user style profiles."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.repositories.style_profile_repo import UserStyleProfileRepository
from app.api.v1.identity.schemas.style_profile import (
    CompleteOnboardingBody,
    OnboardingStatusResponse,
    OnboardingSubmitBody,
    StyleProfileCreate,
    StyleProfileResponse,
    StyleProfileUpdate,
)
from app.core.background import spawn
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client
from app.models.user_style_profile import UserStyleProfile

logger = get_logger("style_profile_service")
settings = get_settings()


def _row_to_response(row: UserStyleProfile) -> StyleProfileResponse:
    return StyleProfileResponse.from_orm_row(row)


def _join_human(items: list | None, max_n: int = 3) -> str:
    """Join a list into a readable phrase: ['a','b','c'] -> 'a, b and c'."""
    vals = [str(i).replace("_", " ").strip() for i in (items or []) if i]
    vals = vals[:max_n]
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    return ", ".join(vals[:-1]) + f" and {vals[-1]}"


def compose_style_summary(row: UserStyleProfile) -> str:
    """
    Build a concise, natural-language style summary using ONLY the user's own
    onboarding answers — no external/AI call. This guarantees the profile reflects
    a summary immediately on submit, and gives outfit generation a stable, canonical
    description to ground every recommendation.
    """
    styles = _join_human(getattr(row, "style_preferences", None))
    occasions = _join_human(getattr(row, "occasion_preferences", None))
    fav = _join_human(getattr(row, "favorite_colors", None))
    avoid = _join_human(getattr(row, "avoided_colors", None))
    fits = _join_human(getattr(row, "fit_preferences", None))
    goals = _join_human(getattr(row, "styling_goals", None), max_n=2)

    sentences: list[str] = []
    if styles:
        sentences.append(f"Your style leans {styles}.")
    if fav and fits:
        sentences.append(f"You favour {fav} tones and prefer a {fits} fit.")
    elif fav:
        sentences.append(f"You favour {fav} tones.")
    elif fits:
        sentences.append(f"You prefer a {fits} fit.")
    if avoid:
        sentences.append(f"You tend to avoid {avoid}.")
    if occasions:
        sentences.append(f"Most of your outfits are for {occasions}.")
    if goals:
        sentences.append(f"Your styling goal is to {goals}.")

    text = " ".join(sentences).strip()
    return text or ("Tell us a bit more about your style preferences to personalise your recommendations.")


def _extract_profile_data(row: UserStyleProfile) -> dict:
    return {
        "user_id": str(row.user_id),
        "gender": row.custom_gender if row.gender == "custom" and row.custom_gender else row.gender,
        "age_range": row.age_range,
        "height": f"{row.height_value} {row.height_unit}" if row.height_value and row.height_unit else None,
        "weight": f"{row.weight_value} {row.weight_unit}" if row.weight_value and row.weight_unit else None,
        "skin_tone": getattr(row, "skin_tone", None),
        "undertone": getattr(row, "undertone", None),
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
        # v2 fields
        "styling_goals": getattr(row, "styling_goals", None) or [],
        "avoidances": getattr(row, "avoidances", None) or [],
        "pattern_preferences": getattr(row, "pattern_preferences", None) or [],
    }


_STYLE_PROFILE_PROMPT = """\
You are ClozeHive AI, an expert personal stylist. Based on the user style profile AND their actual wardrobe data below, \
generate a rich profile JSON used to personalise all AI recommendations.

If wardrobe data is provided, let it shape the style_summary and ai_stylist_context — reflect what they actually own, \
not just what they said they prefer. Look for patterns in their real items.

RESPOND WITH VALID JSON ONLY — no markdown fences, no commentary.

Required JSON schema:
{
  "style_summary": "2-3 sentence natural-language description synthesising their stated preferences AND their actual wardrobe. \
Mention dominant categories, colour palette from real items, occasions covered, and any interesting patterns.",
  "style_archetype": "One of: Classic Minimalist | Streetwear Edge | Bohemian Free Spirit | Corporate Power | Casual Comfort | Romantic Feminine | Outdoorsy Explorer | Eclectic Creative | Athleisure Athlete | Vintage Revivalist",
  "recommendation_rules": {
    "always_include": ["list of must-have item types / attributes"],
    "avoid": ["list of item types / attributes to avoid"],
    "colour_palette": ["3-6 hex codes that suit their preferences and existing wardrobe"],
    "occasion_focus": ["primary occasions to optimise outfits for"],
    "fit_notes": "brief sentence about their fit philosophy"
  },
  "ai_stylist_context": "Single rich paragraph (3-5 sentences) the AI stylist reads before every conversation — includes archetype, key traits, colour story from actual wardrobe, occasions, avoidances, styling goals, and any wardrobe gaps worth noting. Written as if briefing a human stylist."
}
"""


async def _load_wardrobe_stats(user_id: UUID) -> dict:
    """Load a statistical snapshot of the user's closet for AI context."""
    try:
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.closet import ClosetItem

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClosetItem)
                .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
                .order_by(ClosetItem.wear_count.desc())
                .limit(100)
            )
            items = result.scalars().all()
            if not items:
                return {}

            # Aggregate statistics
            from collections import Counter

            categories = Counter(i.category for i in items)
            colors = Counter(i.color for i in items if i.color)
            occasions_flat = [o for i in items for o in (i.occasion or [])]
            occasions = Counter(occasions_flat)
            top_worn = [
                {"name": i.name, "category": i.category, "wear_count": i.wear_count} for i in items if i.wear_count > 1
            ][:5]

            return {
                "total_items": len(items),
                "top_categories": dict(categories.most_common(6)),
                "top_colors": dict(colors.most_common(8)),
                "top_occasions": dict(occasions.most_common(5)),
                "most_worn_items": top_worn,
                "never_worn_count": sum(1 for i in items if i.wear_count == 0),
            }
    except Exception as exc:
        logger.warning("wardrobe_stats_load_failed", user_id=str(user_id), error=str(exc))
        return {}


async def _background_generate_style_summary(user_id: UUID, profile_data: dict) -> None:
    """Run in its own DB session so it never blocks an HTTP response.
    Enriches the AI prompt with the user's real wardrobe statistics so the
    generated summary reflects what they actually own, not just preferences.
    """
    if not settings.openai_api_key:
        return
    from app.api.v1.identity.repositories.style_profile_repo import UserStyleProfileRepository
    from app.db.session import AsyncSessionLocal

    non_empty = {k: v for k, v in profile_data.items() if k != "user_id" and v not in (None, [], {}, "")}

    # Load wardrobe data in parallel with the non-empty check
    wardrobe_stats = await _load_wardrobe_stats(user_id)

    if not non_empty and not wardrobe_stats:
        return

    parts = [f"User style profile:\n{json.dumps(non_empty, indent=2)}"]
    if wardrobe_stats:
        parts.append(
            f"\nActual wardrobe data (from {wardrobe_stats.get('total_items', 0)} uploaded items):\n{json.dumps(wardrobe_stats, indent=2)}"
        )
    user_prompt = "\n".join(parts)
    try:
        client = make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url)
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _STYLE_PROFILE_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
        if not raw:
            return
        data = json.loads(raw)
        summary = data.get("style_summary", "")
        archetype = data.get("style_archetype")
        rec_rules = data.get("recommendation_rules")
        ai_ctx = data.get("ai_stylist_context")
        async with AsyncSessionLocal() as session:
            repo = UserStyleProfileRepository(session)
            row = await repo.get_by_user_id(user_id)
            if row:
                # Don't override the canonical, user-derived summary — only fill
                # it if missing. Archetype/context enrichment is still applied.
                if summary and not (row.style_summary or "").strip():
                    row.style_summary = summary
                if archetype:
                    row.style_archetype = archetype
                if rec_rules:
                    row.recommendation_rules = rec_rules
                if ai_ctx:
                    row.ai_stylist_context = ai_ctx
                session.add(row)
                await session.commit()
                logger.info(
                    "style_profile_ai_generated",
                    user_id=str(user_id),
                    archetype=archetype,
                    summary_chars=len(summary),
                )
    except Exception as exc:
        logger.warning("style_summary_generation_failed", user_id=str(user_id), error=str(exc))


def _schedule_style_summary(row: UserStyleProfile) -> None:
    """Fire-and-forget: schedule summary generation without blocking the caller."""
    profile_data = _extract_profile_data(row)
    spawn(
        _background_generate_style_summary(row.user_id, profile_data),
        name="style_summary",
    )


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
        "skin_tone": data.skin_tone,
        "undertone": data.undertone,
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


async def create_style_profile(
    session: AsyncSession, user_id: UUID, payload: StyleProfileCreate
) -> StyleProfileResponse:
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
    row.style_summary = compose_style_summary(row)
    session.add(row)
    await session.flush()
    await session.refresh(row)
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


async def update_style_profile(
    session: AsyncSession, user_id: UUID, payload: StyleProfileUpdate
) -> StyleProfileResponse:
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if not row:
        base = StyleProfileCreate.model_validate(
            {**StyleProfileCreate().model_dump(), **payload.model_dump(exclude_unset=True)}
        )
        return await create_style_profile(session, user_id, base)
    _apply_update(row, payload)
    row.style_summary = compose_style_summary(row)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info("style_profile_updated", user_id=str(user_id))
    _schedule_style_summary(row)
    return _row_to_response(row)


async def refresh_style_summary(session: AsyncSession, user_id: UUID) -> StyleProfileResponse:
    """Manually trigger re-generation of style_summary/archetype/context using latest wardrobe + profile."""
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if not row:
        row = await create_default_profile_row(session, user_id)
    # Explicit manual refresh: clear the summary so the background AI pass
    # (which otherwise won't override a populated summary) regenerates it.
    row.style_summary = None
    session.add(row)
    await session.flush()
    await session.refresh(row)
    _schedule_style_summary(row)
    return _row_to_response(row)


async def submit_onboarding(session: AsyncSession, user_id: UUID, body: OnboardingSubmitBody) -> StyleProfileResponse:
    """
    Single-call endpoint for the v2 onboarding wizard.
    Saves all answers, marks onboarding complete, then fires background AI generation.
    """
    repo = UserStyleProfileRepository(session)
    row = await repo.get_by_user_id(user_id)
    if not row:
        row = await create_default_profile_row(session, user_id)

    # Apply all submitted fields
    fields = body.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(row, k, v)

    row.onboarding_completed = True
    row.onboarding_skipped = False
    # Immediately derive a canonical summary from the user's own answers so the
    # profile reflects it right away (no external/AI dependency).
    row.style_summary = compose_style_summary(row)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info("onboarding_v2_submitted", user_id=str(user_id))
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
