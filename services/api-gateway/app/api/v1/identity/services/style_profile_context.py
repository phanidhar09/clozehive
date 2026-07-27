"""Build AI prompt context from a persisted style profile + legacy User JSONB fields."""

from __future__ import annotations

import json
import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.repositories.style_profile_repo import UserStyleProfileRepository
from app.api.v1.identity.repositories.user_repo import UserRepository
from app.models.user import User
from app.models.user_style_profile import UserStyleProfile


async def load_profile_gender(session: AsyncSession, user_id: Any) -> str | None:
    """Best-effort raw style-profile gender for the RAG metadata pre-filter.

    Returns the user's stated gender (the specific ``custom_gender`` when gender is
    ``"custom"``), or ``None`` on a missing profile / any failure — so retrieval
    silently degrades to audience-neutral rather than erroring the request. The
    caller maps the raw value onto the corpus partition (see
    ``app.rag.metadata_filter.canonical_gender``).
    """
    try:
        uid = user_id if isinstance(user_id, _uuid.UUID) else _uuid.UUID(str(user_id))
        row = await UserStyleProfileRepository(session).get_by_user_id(uid)
    except Exception:
        return None
    if not row:
        return None
    if row.gender == "custom" and row.custom_gender:
        return row.custom_gender
    return row.gender


def style_profile_table_to_prompt_dict(row: UserStyleProfile) -> dict[str, Any]:
    """Structured dict for JSON injection into LLM user payloads."""
    return {
        "source": "user_style_profiles",
        "gender": row.gender,
        "custom_gender": row.custom_gender,
        "height_value": float(row.height_value) if row.height_value is not None else None,
        "height_unit": row.height_unit,
        "weight_value": float(row.weight_value) if row.weight_value is not None else None,
        "weight_unit": row.weight_unit,
        "age_range": row.age_range,
        "skin_tone": getattr(row, "skin_tone", None),
        "undertone": getattr(row, "undertone", None),
        "body_types": row.body_types or [],
        "custom_body_type": row.custom_body_type,
        "fit_preferences": row.fit_preferences or [],
        "custom_fit_notes": row.custom_fit_notes,
        "size_profile": row.size_profile or {},
        "custom_size_notes": row.custom_size_notes,
        "style_preferences": row.style_preferences or [],
        "favorite_colors": row.favorite_colors or [],
        "avoided_colors": row.avoided_colors or [],
        "neutral_color_preference": row.neutral_color_preference,
        "bold_color_preference": row.bold_color_preference,
        "occasion_preferences": row.occasion_preferences or [],
        "climate_preferences": row.climate_preferences or [],
        "onboarding_completed": row.onboarding_completed,
        "onboarding_skipped": row.onboarding_skipped,
        "style_summary": getattr(row, "style_summary", None),
    }


def style_profile_to_prompt_block(row: UserStyleProfile | None, user: User | None) -> str:
    """
    Human-readable block for system prompts (outfit / packing).
    Falls back to legacy User JSONB columns when the dedicated row is missing or sparse.
    """
    lines: list[str] = []
    if row:
        if getattr(row, "style_summary", None):
            lines.append(f"Summary: {row.style_summary}\n")
        g = row.custom_gender if row.gender == "custom" and row.custom_gender else row.gender
        lines.append(f"- Gender / style identity: {g or 'not provided'}")
        hv, hu = row.height_value, row.height_unit
        if hv is not None and hu:
            lines.append(f"- Height: {hv} {hu}")
        else:
            lines.append("- Height: not provided")
        wv, wu = row.weight_value, row.weight_unit
        if wv is not None and wu:
            lines.append(f"- Weight: {wv} {wu}")
        else:
            lines.append("- Weight: not provided")
        lines.append(f"- Age range: {row.age_range or 'not provided'}")
        skin = getattr(row, "skin_tone", None)
        undertone = getattr(row, "undertone", None)
        if skin or undertone:
            tone = skin or "not provided"
            if undertone:
                tone += f" ({undertone} undertone)"
            lines.append(f"- Skin tone: {tone}")
        else:
            lines.append("- Skin tone: not provided")
        lines.append(f"- Body types: {row.body_types or []}")
        if row.custom_body_type:
            lines.append(f"- Custom body type note: {row.custom_body_type}")
        lines.append(f"- Fit preferences: {row.fit_preferences or []}")
        if row.custom_fit_notes:
            lines.append(f"- Custom fit notes: {row.custom_fit_notes}")
        lines.append(f"- Size profile: {json.dumps(row.size_profile or {}, ensure_ascii=False)}")
        if row.custom_size_notes:
            lines.append(f"- Custom size notes: {row.custom_size_notes}")
        lines.append(f"- Style preferences: {row.style_preferences or []}")
        lines.append(f"- Occasion preferences: {row.occasion_preferences or []}")
        lines.append(f"- Favorite colors: {row.favorite_colors or []}")
        lines.append(f"- Colors to avoid: {row.avoided_colors or []}")
        if row.neutral_color_preference is not None:
            lines.append(f"- Prefers neutral colors: {row.neutral_color_preference}")
        if row.bold_color_preference is not None:
            lines.append(f"- Enjoys bold colors: {row.bold_color_preference}")
        lines.append(f"- Climate / comfort preferences: {row.climate_preferences or []}")
        # v2 onboarding fields
        styling_goals = getattr(row, "styling_goals", None)
        avoidances = getattr(row, "avoidances", None)
        pattern_prefs = getattr(row, "pattern_preferences", None)
        style_archetype = getattr(row, "style_archetype", None)
        ai_ctx = getattr(row, "ai_stylist_context", None)
        rec_rules = getattr(row, "recommendation_rules", None)
        if styling_goals:
            lines.append(f"- Styling goals: {styling_goals}")
        if avoidances:
            lines.append(f"- Items/styles to avoid: {avoidances}")
        if pattern_prefs:
            lines.append(f"- Pattern preferences: {pattern_prefs}")
        if style_archetype:
            lines.append(f"- Style archetype: {style_archetype}")
        if rec_rules and isinstance(rec_rules, dict):
            if rec_rules.get("always_include"):
                lines.append(f"- Always include in recommendations: {rec_rules['always_include']}")
            if rec_rules.get("avoid"):
                lines.append(f"- Recommendation avoidances: {rec_rules['avoid']}")
            if rec_rules.get("fit_notes"):
                lines.append(f"- Fit notes: {rec_rules['fit_notes']}")
        if ai_ctx:
            lines.insert(0, f"AI Stylist Brief: {ai_ctx}\n")
    elif user:
        bp = user.body_profile if isinstance(user.body_profile, dict) else None
        sp = user.style_profile if isinstance(user.style_profile, dict) else None
        pr = user.preferences if isinstance(user.preferences, dict) else None
        if bp:
            lines.append(f"- Legacy body_profile: {json.dumps(bp, ensure_ascii=False)}")
        if sp:
            lines.append(f"- Legacy style_profile: {json.dumps(sp, ensure_ascii=False)}")
        if pr:
            lines.append(f"- Legacy preferences: {json.dumps(pr, ensure_ascii=False)}")
    if not lines:
        return ""
    return "User Style Profile Context:\n" + "\n".join(lines)


def merge_user_profile_for_ai(
    user: User | None,
    style_row: UserStyleProfile | None,
) -> dict[str, Any] | None:
    """
    Combined personalization blob for existing AI endpoints that expect
    body_profile / style_profile / preferences, plus the dedicated style_profiles key.
    """
    out: dict[str, Any] = {}
    if user:
        if user.body_profile:
            out["body_profile"] = user.body_profile
        if user.style_profile:
            out["style_profile"] = user.style_profile
        if user.preferences:
            out["preferences"] = user.preferences
    if style_row:
        out["user_style_profile"] = style_profile_table_to_prompt_dict(style_row)
        out["style_profile_context_text"] = style_profile_to_prompt_block(style_row, None)
    elif user and (user.body_profile or user.style_profile or user.preferences):
        out["style_profile_context_text"] = style_profile_to_prompt_block(None, user)
    return out or None


async def load_merged_user_profile_for_ai(
    session: AsyncSession,
    user_id: Any,
    override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Used by outfit/packing/chat routes. `user_id` is UUID."""
    if override:
        return override
    user = await UserRepository(session).get(user_id)
    row = await UserStyleProfileRepository(session).get_by_user_id(user_id)
    return merge_user_profile_for_ai(user, row)
