"""Shared helpers for building personalisation prompt suffixes from user style profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.user_style_profile import UserStyleProfile


def profile_to_context(profile: "UserStyleProfile") -> dict[str, Any]:
    """Convert a UserStyleProfile SQLAlchemy model to a plain dict for prompt injection."""
    return {
        "gender": profile.gender,
        "custom_gender": profile.custom_gender,
        "height_value": profile.height_value,
        "height_unit": profile.height_unit,
        "skin_tone": profile.skin_tone,
        "undertone": profile.undertone,
        "body_types": list(profile.body_types or []),
        "fit_preferences": list(profile.fit_preferences or []),
        "style_preferences": list(profile.style_preferences or []),
        "favorite_colors": list(profile.favorite_colors or []),
        "avoided_colors": list(profile.avoided_colors or []),
        "occasion_preferences": list(profile.occasion_preferences or []),
        "style_archetype": profile.style_archetype,
    }


def build_user_context_suffix(user_context: dict[str, Any] | None) -> str:
    """Return a prompt block that personalises AI garment analysis for the given user."""
    if not user_context:
        return ""
    parts: list[str] = []

    gender = user_context.get("gender")
    if gender and gender not in ("prefer_not_to_say", "custom", ""):
        parts.append(f"Gender: {gender}")

    body_types = user_context.get("body_types") or []
    if body_types:
        parts.append(f"Body type: {', '.join(body_types)}")

    height_val = user_context.get("height_value")
    if height_val:
        parts.append(f"Height: {height_val} {user_context.get('height_unit', 'cm')}")

    skin_tone = user_context.get("skin_tone")
    undertone = user_context.get("undertone")
    if skin_tone:
        tone = skin_tone + (f" ({undertone} undertone)" if undertone else "")
        parts.append(f"Skin tone: {tone}")

    style_prefs = user_context.get("style_preferences") or []
    if style_prefs:
        parts.append(f"Style preferences: {', '.join(style_prefs)}")

    fav_colors = user_context.get("favorite_colors") or []
    if fav_colors:
        parts.append(f"Favourite colours: {', '.join(fav_colors)}")

    avoided_colors = user_context.get("avoided_colors") or []
    if avoided_colors:
        parts.append(f"Avoided colours: {', '.join(avoided_colors)}")

    occ_prefs = user_context.get("occasion_preferences") or []
    if occ_prefs:
        parts.append(f"Occasion preferences: {', '.join(occ_prefs)}")

    if not parts:
        return ""

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "USER PROFILE — personalise your output:",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ] + [f"• {p}" for p in parts] + [
        "",
        "Apply this profile to:",
        "• Set gender field on each item to match the user's gender where appropriate",
        "• Assign occasion_tags that align with the user's stated occasion preferences",
        "• Prioritise style_tags matching the user's style preferences",
        "• For skin tone: describe primary_color using terms that consider the user's complexion",
        "• For traditional/religious/cultural garments, identify by specific name in subcategory:",
        "  saree, kurta, salwar kameez, lehenga, sherwani, churidar, dupatta, choli, dhoti,",
        "  abaya, hijab, thobe/thoub, kaftan, jalabiya, kimono, hanbok, ao dai, dirndl,",
        "  pagri/turban, bandhgala, achkan, anarkali, ghagra, patiala, mekhela chador.",
        "• When a traditional garment is detected, add the relevant festival/occasion to",
        "  occasion_tags: diwali, navratri, eid, holi, christmas, wedding, durga puja, etc.",
    ]
    return "\n".join(lines)
