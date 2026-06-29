"""Shopping Check Service — in-store buy/skip advisor.

Flow:
1. Vision AI analyses the photo → extracts item attributes
2. Embedding generated for the new item description
3. pgvector similarity search against user's closet_items
4. Scoring engine computes buy_score (0–100) — weighted %, closet-fit first,
   then personal fit, then coverage (cost is NOT a factor; it's a side signal):
   - Compatibility (35%)  — pairs with items already owned
   - Style match (25%)    — coloring / fit / taste vs the user's style profile
   - Uniqueness (20%)     — not a near-duplicate (a veto on re-buying)
   - Gap fill (10%)       — fills a detected purchase_gap
   - Occasion/season coverage (5% each)
   When the user has no style profile, the style_match weight folds back into
   the closet-evidence factors (see effective_weights).
5. Recommendation + reasoning returned
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services import ai_service
from app.api.v1.intelligence.services.fashion_rag_service import (
    get_fashion_context_for_prompt,
    search_fashion_knowledge,
)
from app.api.v1.wardrobe.services.vision_service import analyze_for_bulk
from app.core import outfit_compatibility as compat
from app.core.embedding_service import (
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
    vector_literal,
)
from app.core.logging import get_logger

logger = get_logger("shopping_check_service")


def parse_price_to_float(raw: Any) -> float | None:
    """Best-effort parse of a scraped price string into a positive float.

    OG/JSON-LD prices arrive as free-form strings ("$129.99", "USD 1,299.00",
    "1.299,00 €", "129,99"). We isolate the first numeric run and resolve the
    decimal separator by position so both US (1,299.00) and EU (1.299,00)
    formats land correctly. Returns None for anything non-positive or unparseable
    so a bad scrape never writes a junk price.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None

    match = re.search(r"\d[\d.,\s]*", str(raw))
    if not match:
        return None
    num = match.group(0).strip().replace(" ", "")

    if "," in num and "." in num:
        # Whichever separator appears last is the decimal point.
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        # Comma alone: decimal if it's a trailing ",dd", else a thousands sep.
        num = num.replace(",", ".") if re.search(r",\d{2}$", num) else num.replace(",", "")

    try:
        val = float(num)
    except ValueError:
        return None
    return round(val, 2) if val > 0 else None


# ── Scoring weights ──────────────────────────────────────────────────────────
_DUPLICATE_THRESHOLD = 0.88  # cosine sim — item is "essentially the same" (dupe-check only)

# Steers vision when the input is a rendered product-PAGE screenshot (the fallback
# for bot-blocked retailers) rather than a clean garment photo. Without this the
# model labels the whole page "other" and compatibility finds nothing to pair.
_SCREENSHOT_VISION_HINT = (
    "IMPORTANT CONTEXT: This image is a SCREENSHOT of an online clothing-store "
    "product page — not a clean studio photo. It may include site navigation, "
    "buttons, price text, thumbnails of other products, and a model wearing "
    "several garments. Identify the SINGLE main product this page is selling "
    "(usually the largest central garment, matching the page title). Describe "
    "ONLY that item. Ignore site chrome, navigation, related-product thumbnails, "
    "and any secondary garments the model also wears. Always assign a concrete "
    "category (tops, bottoms, shoes, outerwear, dresses, accessories) — never "
    "'other' — by inferring the main product's type."
)

# Percentage-weighted scoring: each factor weight is the % it can contribute, and
# the weights SUM TO 100. buy_score = Σ(weight × factor_subscore) where each
# subscore is 0–1, so the result is a true 0–100% with no clamping needed.
#
# Ordering of intent: closet-fit FIRST (does it pair with what you own, without
# being a re-buy), then PERSONAL fit (your coloring / fit / taste), then the
# coverage extras. Cost is deliberately NOT a factor here — it's surfaced as a
# separate side signal so a taste/closet verdict is never driven by price.
_WEIGHTS: dict[str, float] = {
    "compatibility": 35.0,  # genuinely *pairs* with items already in the closet
    "style_match": 25.0,  # matches your stated coloring / fit / taste (profile)
    "uniqueness": 20.0,  # not a near-duplicate — still a strong veto on re-buying
    "gap_fill": 10.0,  # fills a detected category gap
    "occasion_new": 5.0,  # adds new occasion coverage
    "season_new": 5.0,  # adds new season coverage
}
assert round(sum(_WEIGHTS.values())) == 100, "buy_score weights must sum to 100%"
# When the user has no usable style profile (skipped onboarding), we can't judge
# personal fit — so style_match's weight is folded back into the closet-evidence
# factors (these), proportional to their weight, rather than silently zeroing 25%.
_CLOSET_EVIDENCE_FACTORS = ("compatibility", "uniqueness")
_COMPAT_SATURATION = 4  # this many genuine pairings = full compatibility credit
# Embedding-similarity cutoff for the dupe-check (a near-identical item). This is
# ONLY used for "do you already own this" — never for "does this match".
_DUPE_FETCH_LIMIT = 12
# Cap how many closet items we role-score for compatibility (closets are small).
_COMPAT_CLOSET_LIMIT = 200


# ── Instrumentation ───────────────────────────────────────────────────────────

# The Shop with FANI funnel. Logged from line one so repeat-paste (retention) and
# act-on-verdict (intent) are measurable from the first user.
SHOPPING_EVENT_TYPES = frozenset(
    {
        "check_created",  # a verdict was produced (photo or URL)
        "verdict_viewed",  # user actually saw the result card
        "outfit_opened",  # user expanded the matched/pairing items
        "verdict_acted",  # user recorded a buy/skip decision
        "added_to_closet",  # user saved the item
        "paste_again",  # user started another check from the result
    }
)


async def record_shopping_event(
    session: AsyncSession,
    user_id: str,
    event_type: str,
    check_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Best-effort funnel event write. Never raises into the caller — analytics
    must not break a verdict. Returns True if a row was written."""
    if event_type not in SHOPPING_EVENT_TYPES:
        logger.warning("shopping_event_unknown_type", event_type=event_type)
        return False
    import json as _json

    try:
        await session.execute(
            text("""
                INSERT INTO shopping_events (id, user_id, check_id, event_type, metadata, created_at)
                VALUES (gen_random_uuid(), CAST(:uid AS uuid),
                        CAST(:cid AS uuid), :etype, CAST(:meta AS jsonb), NOW())
            """),
            {
                "uid": user_id,
                "cid": check_id,
                "etype": event_type,
                "meta": _json.dumps(metadata) if metadata is not None else None,
            },
        )
        await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — instrumentation is never load-bearing
        logger.warning("shopping_event_write_failed", event_type=event_type, error=str(exc))
        return False


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_item_text(analysis: dict[str, Any]) -> str:
    """
    Convert vision analysis payload into embedding text.
    Pass both alias variants so item_to_embedding_text resolves whichever is populated.
    """
    return item_to_embedding_text(
        {
            # Both naming conventions kept — _resolve() picks the first non-empty one
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "subcategory": analysis.get("subcategory", ""),
            "color": analysis.get("color", ""),
            "primary_color": analysis.get("primary_color", ""),
            "fabric": analysis.get("fabric", ""),
            "material": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "fit": analysis.get("fit", ""),
            "season": analysis.get("season") or [],
            "season_tags": analysis.get("season_tags") or [],
            "occasion": analysis.get("occasion") or [],
            "occasion_tags": analysis.get("occasion_tags") or [],
            "tags": analysis.get("tags") or [],
            "style_tags": analysis.get("style_tags") or [],
            "notes": analysis.get("notes", ""),
            "description": analysis.get("description", ""),
            "brand": analysis.get("brand", ""),
            "secondary_colors": analysis.get("secondary_colors") or [],
        }
    )


async def _fetch_existing_occasions_seasons(session: AsyncSession, user_id: str) -> tuple[set[str], set[str]]:
    """Return sets of occasions and seasons already covered by the user's closet."""
    sql = text("""
        SELECT occasion, season FROM closet_items
        WHERE user_id = CAST(:uid AS uuid) AND is_archived = false
    """)
    result = await session.execute(sql, {"uid": user_id})
    rows = result.mappings().all()
    occasions: set[str] = set()
    seasons: set[str] = set()
    for row in rows:
        for occ in row["occasion"] or []:
            occasions.add(occ.lower())
        for s in row["season"] or []:
            seasons.add(s.lower())
    return occasions, seasons


async def _has_open_gap_for_category(session: AsyncSession, user_id: str, category: str) -> bool:
    """Return True if there's an unresolved purchase gap for this category."""
    sql = text("""
        SELECT 1 FROM purchase_gaps
        WHERE user_id = CAST(:uid AS uuid)
          AND resolved = false
          AND LOWER(missing_category) = LOWER(:cat)
        LIMIT 1
    """)
    result = await session.execute(sql, {"uid": user_id, "cat": category})
    return result.first() is not None


async def _fetch_closet_for_compat(session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """Fetch the user's available closet items with the attributes compatibility
    scoring needs. Unlike the embedding search, this returns the WHOLE closet
    (capped) so role-complementary items — the things the pasted item pairs with,
    which embedding similarity never surfaces — are actually considered.

    Only AVAILABLE items are styled (in-laundry / at-cleaners / lent-out excluded),
    matching the rest of the styling pipeline.
    """
    sql = text("""
        SELECT id, name, category, color, fabric, pattern, season, occasion,
               image_url, processed_image_url, wear_count
        FROM closet_items
        WHERE user_id = CAST(:uid AS uuid)
          AND is_archived = false
          AND COALESCE(availability, 'available') = 'available'
        ORDER BY wear_count DESC NULLS LAST, created_at DESC
        LIMIT :lim
    """)
    result = await session.execute(sql, {"uid": user_id, "lim": _COMPAT_CLOSET_LIMIT})
    return [dict(r) for r in result.mappings().all()]


# ── Scoring engine (pure) ──────────────────────────────────────────────────────


def to_ten_point(score_100: float) -> float:
    """Headline buy score on a 0–10 scale (one decimal), derived from the 0–100
    score. The 0–100 form stays canonical — DB column, per-factor breakdown, and
    the recommendation bands all use it — so this is purely the display number
    (e.g. 82 → 8.2). Keeping one source of truth means stored history and the
    "earned / max" bars never disagree with the headline."""
    return round(max(0.0, min(100.0, float(score_100))) / 10.0, 1)


# The verdict is communicated as a 0–10 RATING plus a colour — never as a
# "buy / skip / consider" instruction. The colour bands mirror the score bands:
#   green  → strong fit   (score ≥ 70 / rating ≥ 7.0)
#   amber  → middling fit  (45–69 / 4.5–6.9)
#   red    → weak fit      (< 45 / < 4.5)
_RATING_COLORS = ("red", "amber", "green")


def rating_color(score_100: float) -> str:
    """Colour token for a score's band — the user sees a rating + this colour
    instead of a buy/skip word."""
    if score_100 >= 70:
        return "green"
    if score_100 >= 45:
        return "amber"
    return "red"


def effective_weights(*, has_profile: bool) -> dict[str, float]:
    """The weight map actually used for a given user.

    With a profile, the canonical :data:`_WEIGHTS` apply. Without one we can't
    judge personal fit, so ``style_match``'s weight is folded into the closet-
    evidence factors (proportional to their weight) — the score still sums to 100
    and leans harder on closet signal instead of punishing a missing profile.
    """
    if has_profile:
        return dict(_WEIGHTS)
    weights = dict(_WEIGHTS)
    style_w = weights.pop("style_match")
    base = sum(weights[k] for k in _CLOSET_EVIDENCE_FACTORS)
    for k in _CLOSET_EVIDENCE_FACTORS:
        weights[k] += style_w * weights[k] / base
    return weights


def compute_buy_score(
    *,
    has_duplicate: bool,
    compatible_count: int,
    fills_gap: bool,
    has_new_occasions: bool,
    has_new_seasons: bool,
    style_match: float | None = None,
) -> tuple[int, dict[str, float], str, dict[str, float]]:
    """Pure scoring core — given the closet- and profile-derived signals, return
    the 0–100 buy score, its per-factor % breakdown, the recommendation band, and
    the effective weights used (so the UI can render "earned / max" bars).

    ``style_match`` is the 0–1 personal-fit subscore (coloring / fit / taste).
    Pass ``None`` when the user has no usable profile — its weight is then folded
    into the closet-evidence factors via :func:`effective_weights`.

    Extracted from :func:`analyze_shopping_item` so the product's most important
    number is unit-testable in isolation (no vision/embeddings/DB needed).
    """
    has_profile = style_match is not None
    weights = effective_weights(has_profile=has_profile)

    subscores: dict[str, float] = {
        "uniqueness": 0.0 if has_duplicate else 1.0,
        "compatibility": min(compatible_count / _COMPAT_SATURATION, 1.0),
        "gap_fill": 1.0 if fills_gap else 0.0,
        # Novelty only counts when the item isn't a duplicate.
        "occasion_new": 1.0 if (has_new_occasions and not has_duplicate) else 0.0,
        "season_new": 1.0 if (has_new_seasons and not has_duplicate) else 0.0,
    }
    if style_match is not None:
        subscores["style_match"] = max(0.0, min(1.0, style_match))

    score_breakdown = {k: round(weights[k] * subscores[k], 1) for k in weights}
    score = max(0, min(100, round(sum(score_breakdown.values()))))

    if score >= 70:
        recommendation = "buy"
    elif score >= 45:
        recommendation = "consider"
    else:
        recommendation = "skip"
    return score, score_breakdown, recommendation, weights


# ── Personal-fit alignment (profile-driven) ────────────────────────────────────

# Undertone → the chromatic warmth (in compat's hue space, 0–360) it flatters.
# A coarse but honest nudge: warm undertones suit warm hues (reds→yellows),
# cool undertones suit cool hues (greens→purples). Neutrals/unknowns are skipped.
_WARM_HUE_RANGE = (0.0, 70.0)  # red, orange, amber, mustard, olive-ish
_COOL_HUE_RANGE = (120.0, 300.0)  # green, teal, blue, indigo, purple


def _profile_tokens(values: Any) -> set[str]:
    """Lowercased, stripped token set from a JSON list/str profile field."""
    out: set[str] = set()
    if isinstance(values, list):
        for v in values:
            s = str(v).strip().lower()
            if s:
                out.add(s)
    elif isinstance(values, str) and values.strip():
        out.add(values.strip().lower())
    return out


def _matches_any(needle: str, tokens: set[str]) -> bool:
    """Loose membership: ``needle`` matches a token if either contains the other
    (so "navy" matches a "navy blue" item color, and vice-versa)."""
    needle = needle.strip().lower()
    if not needle:
        return False
    return any(needle in t or t in needle for t in tokens)


def compute_style_alignment(
    analysis: dict[str, Any],
    profile: dict[str, Any] | None,
) -> tuple[float | None, list[str]]:
    """Score how well a candidate item matches the user's *personal* preferences —
    coloring, fit, and taste — independent of their closet. Pure & unit-testable.

    Returns ``(subscore, reasons)`` where subscore is 0–1, or ``(None, [])`` when
    the profile carries no usable signal (empty / skipped onboarding) so the
    caller can redistribute the weight instead of scoring a phantom 0.

    Honesty boundary: this is preference & coloring alignment, NOT a physical-fit
    prediction — a product photo can't tell us whether a garment will fit a body.
    We score declared ``fit_preferences`` against the item's detected ``fit`` and
    flag explicit ``avoidances``; we never claim a size will fit.
    """
    if not profile:
        return None, []

    components: list[float] = []
    reasons: list[str] = []

    from app.core import outfit_compatibility as _compat

    # ── Colour: favourites (+), avoided (−), undertone nudge ──────────────────
    item_colors = [
        str(analysis.get("primary_color") or analysis.get("color") or "").strip().lower(),
        *[str(c).strip().lower() for c in (analysis.get("secondary_colors") or [])],
    ]
    item_colors = [c for c in item_colors if c]
    fav = _profile_tokens(profile.get("favorite_colors"))
    avoid = _profile_tokens(profile.get("avoided_colors"))
    if item_colors and (fav or avoid):
        if any(_matches_any(c, avoid) for c in item_colors):
            components.append(0.1)
            reasons.append("In a color you usually avoid.")
        elif any(_matches_any(c, fav) for c in item_colors):
            components.append(1.0)
            reasons.append("In one of your favorite colors.")
        else:
            # Not loved, not hated — let undertone break the tie if we can read it.
            undertone = str(profile.get("undertone") or "").strip().lower()
            primary = item_colors[0]
            kind, hue = _compat.color_profile(primary)
            if undertone in ("warm", "cool") and kind == "chromatic" and hue is not None:
                warm = _WARM_HUE_RANGE[0] <= hue <= _WARM_HUE_RANGE[1]
                cool = _COOL_HUE_RANGE[0] <= hue <= _COOL_HUE_RANGE[1]
                if (undertone == "warm" and warm) or (undertone == "cool" and cool):
                    components.append(0.85)
                    reasons.append(f"Flatters your {undertone} undertone.")
                elif (undertone == "warm" and cool) or (undertone == "cool" and warm):
                    components.append(0.45)
                else:
                    components.append(0.6)
            else:
                components.append(0.6)

    # ── Fit: declared preferences (+) vs avoidances (−). Preference, not size. ──
    item_fit = str(analysis.get("fit") or "").strip().lower()
    fit_prefs = _profile_tokens(profile.get("fit_preferences"))
    avoidances = _profile_tokens(profile.get("avoidances"))
    if item_fit and (fit_prefs or avoidances):
        if _matches_any(item_fit, avoidances):
            components.append(0.1)
            reasons.append(f"A {item_fit} fit, which you've said you avoid.")
        elif _matches_any(item_fit, fit_prefs):
            components.append(1.0)
            reasons.append(f"A {item_fit} fit, just how you like it.")
        else:
            components.append(0.5)

    # ── Taste: item style tags vs preferred styles / archetype ────────────────
    item_styles = _profile_tokens(analysis.get("style_tags"))
    pref_styles = _profile_tokens(profile.get("style_preferences"))
    archetype = str(profile.get("style_archetype") or "").strip().lower()
    if archetype:
        pref_styles.add(archetype)
    if item_styles and pref_styles:
        if item_styles & pref_styles or any(_matches_any(s, pref_styles) for s in item_styles):
            components.append(1.0)
            reasons.append("Fits your usual style.")
        else:
            components.append(0.5)

    # Avoidances can also reference whole garment types ("crop tops") — let an
    # explicit avoidance on name/category drag the score down even when fit was
    # unreadable, so we never call an avoided piece a great personal match.
    name_blob = " ".join(str(analysis.get(k) or "").lower() for k in ("name", "subcategory", "category"))
    if avoidances and any(tok in name_blob for tok in avoidances if len(tok) >= 4):
        components.append(0.1)
        reasons.append("Matches something on your avoid list.")

    if not components:
        return None, []
    return sum(components) / len(components), reasons


def _profile_to_match_dict(row: Any) -> dict[str, Any]:
    """Extract just the fields :func:`compute_style_alignment` needs from a
    ``UserStyleProfile`` row, as a plain dict (keeps scoring pure & testable)."""
    return {
        "favorite_colors": row.favorite_colors or [],
        "avoided_colors": row.avoided_colors or [],
        "undertone": row.undertone,
        "fit_preferences": row.fit_preferences or [],
        "avoidances": row.avoidances or [],
        "style_preferences": row.style_preferences or [],
        "style_archetype": row.style_archetype,
    }


async def _load_style_match_profile(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    """Best-effort load of the user's style profile for personal-fit scoring.
    Returns None (→ weight redistributes to closet factors) on any miss/error."""
    from app.api.v1.identity.repositories.style_profile_repo import UserStyleProfileRepository

    try:
        row = await UserStyleProfileRepository(session).get_by_user_id(uuid.UUID(user_id))
    except Exception as exc:  # noqa: BLE001 — scoring must survive a profile miss
        logger.warning("shopping_profile_load_failed", error=str(exc))
        return None
    return _profile_to_match_dict(row) if row else None


# ── RAG-grounded verdict ("FANI's Take") ───────────────────────────────────────

# The deterministic score is AUTHORITATIVE. The model may only *explain* it using
# retrieved, cited fashion knowledge — it is structurally prevented from inventing
# items/brands/numbers because every fact it's allowed to use is supplied below and
# out-of-range citations are dropped after parsing.
_SHOPPING_TAKE_SYSTEM = """You are FANI, a professional AI fashion stylist. You give the user an honest
RATING of how well an item fits their wardrobe and taste — a 0–10 score with a colour
(green = strong fit, amber = middling, red = weak fit).

You receive two things:
1. [VERDICT FACTS] — computed from the user's REAL closet. These are AUTHORITATIVE and final.
2. [FASHION KNOWLEDGE] — retrieved styling rules, each tagged [SOURCE-N].

Write a short, confident take (2-3 sentences, second person) that EXPLAINS what the rating means.

WORDING RULE — mandatory:
- NEVER tell the user to "buy", "skip", "consider", "purchase", "get it", "pass", or "add to cart".
  Do not give a purchase instruction at all.
- Always frame your take around the RATING and its COLOUR (e.g. "a strong 8.2/10 — green").
  Explain *why* the rating is what it is using the facts; let the user decide.

GROUNDING RULES — mandatory; they override any styling intuition:
- The VERDICT FACTS are true. Never contradict them, and never state a number that isn't given.
- NEVER invent owned items, brands, prices, retailers, or attributes. Reference the user's own
  items only by the exact names listed in the facts (if any are listed).
- Base every styling claim on [FASHION KNOWLEDGE] and cite it inline as [SOURCE-N] using the exact
  tag. If the knowledge does not cover a point, give conservative, widely-accepted advice and do
  NOT cite a source — never fabricate a citation.
- Be honest: if the facts say it's a duplicate or pairs with nothing, say so plainly.

Return ONLY a json object: {"verdict": "<2-3 sentence take>", "cited_sources": [<source numbers you cited>]}"""


async def _generate_grounded_take(
    session: AsyncSession,
    *,
    analysis: dict[str, Any],
    score: int,
    dupe_count: int,
    pairing_names: list[str],
    compatible_count: int,
    fills_gap: bool,
    new_occasions: set[str],
    new_seasons: set[str],
    category: str,
) -> dict[str, Any] | None:
    """Produce a RAG-grounded natural-language verdict layered on top of the
    deterministic score. Best-effort: returns None (caller keeps the templated
    reasoning) when no knowledge is retrieved or the model output is unusable.
    """
    color = analysis.get("primary_color") or analysis.get("color") or ""
    name = analysis.get("name") or category or "this item"
    item_occasions = ", ".join(analysis.get("occasion_tags") or []) or "unspecified"

    rag_query = (
        f"Is a {color} {category} worth buying? How to style and pair it, "
        f"what to wear it with, suitable occasions ({item_occasions})."
    )
    docs = await search_fashion_knowledge(session, rag_query, limit=3)
    if not docs:
        return None  # nothing to ground on → keep the deterministic reasoning only

    knowledge_block = "\n\n".join(f"[SOURCE-{i}] {d['title']}\n{d['content'][:500]}" for i, d in enumerate(docs, 1))

    pairs_fact = (
        f"Pairs with {compatible_count} owned item(s): {', '.join(pairing_names)}."
        if pairing_names
        else "Does not clearly pair with anything currently in the closet."
    )
    facts = (
        "[VERDICT FACTS]\n"
        f"- Item: {name} ({color} {category}).\n"
        f"- Rating: {to_ten_point(score)}/10 ({rating_color(score)}).\n"
        f"- {('You already own ' + str(dupe_count) + ' near-identical item(s).') if dupe_count else 'Not a duplicate of anything you own.'}\n"
        f"- {pairs_fact}\n"
        f"- {('Fills a gap in your ' + category + ' collection.') if fills_gap else 'Does not fill a flagged wardrobe gap.'}\n"
        f"- New occasions it would add: {', '.join(sorted(new_occasions)) or 'none'}.\n"
        f"- New seasons it would add: {', '.join(sorted(new_seasons)) or 'none'}.\n"
    )
    user_msg = (
        f"{facts}\n\n[FASHION KNOWLEDGE — cite [SOURCE-N] when you use a rule]\n"
        f"{knowledge_block}\n[END FASHION KNOWLEDGE]\n\n"
        "Write the verdict now. Explain the facts above using the fashion knowledge and cite "
        "[SOURCE-N]. Do not invent items, brands, prices, or numbers."
    )

    raw = await ai_service.chat(
        messages=[{"role": "user", "content": user_msg}],
        system_prompt=_SHOPPING_TAKE_SYSTEM,
        use_json_mode=True,
        temperature=0.2,
        max_tokens=300,
    )

    import json as _json

    try:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        data = _json.loads(cleaned)
    except Exception:
        logger.warning("shopping_take_unparseable", raw=raw[:160])
        return None

    verdict = str(data.get("verdict") or "").strip()
    if not verdict:
        return None

    # Map cited source numbers → titles for audit/UI. Out-of-range numbers the
    # model may emit are dropped — a hallucinated citation never reaches the user.
    cited_titles: list[str] = []
    for n in data.get("cited_sources") or []:
        try:
            idx = int(n) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(docs) and docs[idx]["title"] not in cited_titles:
            cited_titles.append(docs[idx]["title"])

    return {"take": verdict, "cited_titles": cited_titles, "grounded": True}


# ── Core analysis ─────────────────────────────────────────────────────────────


async def analyze_shopping_item(
    image_bytes: bytes,
    media_type: str,
    user_id: str,
    session: AsyncSession,
    image_url: str | None = None,
    *,
    input_type: str = "photo",
    source_url: str | None = None,
    product_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Analyse a shopping item photo against the user's closet and return a
    buy recommendation with percentage score.

    ``input_type`` records how the image was sourced ("photo" upload, "url"
    product image, or "screenshot" page render). ``product_meta`` carries the
    OG/JSON-LD fields pulled from a pasted product URL — used both to enrich the
    vision analysis (brand/name the photo can't reveal) and for attribution.
    """
    # 1. Vision analysis. A page screenshot needs extra steering — it contains
    #    site chrome, price text, and thumbnails of other products, so the model
    #    must pick the single main garment instead of assuming one clean photo.
    extra_instruction: str | None = None
    if input_type == "screenshot":
        extra_instruction = _SCREENSHOT_VISION_HINT
        name_hint = (product_meta or {}).get("title")
        if name_hint:
            extra_instruction += (
                f'\n\nThe page title/URL indicates the product is: "{name_hint}". '
                "Identify and describe THAT garment specifically."
            )
    analysis = await analyze_for_bulk(image_bytes, media_type, extra_instruction=extra_instruction)

    # 1b. Enrich with product-page metadata the image alone can't reveal (brand,
    #     marketed name, price) and keep the source for attribution in the UI.
    if product_meta:
        if product_meta.get("brand") and not analysis.get("brand"):
            analysis["brand"] = product_meta["brand"]
        if product_meta.get("title") and not analysis.get("name"):
            analysis["name"] = product_meta["title"]
        analysis["source_url"] = source_url or product_meta.get("source_url")
        analysis["source_title"] = product_meta.get("title")
        analysis["source_brand"] = product_meta.get("brand")
        analysis["source_price"] = product_meta.get("price")
        analysis["source_site"] = product_meta.get("site_name")

    item_text = _build_item_text(analysis)
    category = analysis.get("category", "").lower()

    # 2. Embed the new item — used ONLY for the dupe-check ("do you own this").
    embedding = await generate_text_embedding(item_text)

    # 3a. DUPE-CHECK (embedding similarity). High cosine similarity = a near-
    #     identical garment (another navy blazer). This is the honesty signal,
    #     deliberately kept apart from compatibility.
    dupe_candidates: list[dict[str, Any]] = []
    if embedding:
        dupe_candidates = await pgvector_cosine_search(
            session=session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=_DUPE_FETCH_LIMIT,
            threshold=_DUPLICATE_THRESHOLD,
            filter_archived=True,
        )
    dupe_items = [it for it in dupe_candidates if float(it.get("similarity_score", 0)) >= _DUPLICATE_THRESHOLD]
    has_duplicate = bool(dupe_items)
    dupe_ids = {str(it.get("id", "")) for it in dupe_items}

    # 3b. COMPATIBILITY (does this *go with* what I own). Score the pasted item
    #     against role-complementary closet items — the matches embedding search
    #     can never surface. A blazer is scored against bottoms/shoes/layers,
    #     not against other blazers.
    closet = await _fetch_closet_for_compat(session, user_id)
    pairings: list[dict[str, Any]] = []
    for owned in closet:
        if str(owned.get("id", "")) in dupe_ids:
            continue  # a duplicate isn't a "pairing"
        result = compat.score_compatibility(analysis, owned)
        if result["pairs"]:
            pairings.append(
                {
                    "id": str(owned.get("id", "")),
                    "name": owned.get("name", ""),
                    "category": owned.get("category", ""),
                    "color": owned.get("color", ""),
                    "image_url": owned.get("processed_image_url") or owned.get("image_url"),
                    "similarity_score": result["score"],  # compatibility, not embedding
                    "is_duplicate": False,
                    "compat_reasons": result["reasons"],
                }
            )
    pairings.sort(key=lambda p: p["similarity_score"], reverse=True)
    compatible_count = len(pairings)

    # 4. Existing coverage
    owned_occasions, owned_seasons = await _fetch_existing_occasions_seasons(session, user_id)

    # 5. Compute percentage-weighted score — each factor yields a 0–1 subscore,
    #    contributes (weight × subscore) %, and all weights sum to 100.
    reasons: list[str] = []

    item_occasions = {o.lower() for o in (analysis.get("occasion_tags") or [])}
    new_occasions = item_occasions - owned_occasions
    item_seasons = {s.lower() for s in (analysis.get("season_tags") or [])}
    new_seasons = item_seasons - owned_seasons
    fills_gap = bool(category and await _has_open_gap_for_category(session, user_id, category))

    # Personal-fit signal: coloring / fit / taste vs the user's style profile.
    # None when there's no usable profile → its weight folds into closet factors.
    profile = await _load_style_match_profile(session, user_id)
    style_match, style_reasons = compute_style_alignment(analysis, profile)

    # Pure scoring core — see compute_buy_score (unit-tested in isolation).
    score, score_breakdown, recommendation, weights_used = compute_buy_score(
        has_duplicate=has_duplicate,
        compatible_count=compatible_count,
        fills_gap=fills_gap,
        has_new_occasions=bool(new_occasions),
        has_new_seasons=bool(new_seasons),
        style_match=style_match,
    )

    # Human-readable reasons mirror the factors that contributed.
    if has_duplicate:
        reasons.append(f"You already own {len(dupe_items)} very similar item(s).")
    if pairings:
        sample = ", ".join(p["name"] for p in pairings[:3] if p["name"])
        tail = f" (e.g. {sample})" if sample else ""
        reasons.append(f"Pairs with {compatible_count} item(s) you already own{tail}.")
    else:
        reasons.append("Doesn't clearly pair with anything in your closet yet.")
    if fills_gap:
        reasons.append(f"Fills a detected gap in your {category} collection.")
    if new_occasions and not has_duplicate:
        reasons.append(f"Adds new occasion coverage: {', '.join(new_occasions)}.")
    if new_seasons and not has_duplicate:
        reasons.append(f"Extends your wardrobe into: {', '.join(new_seasons)}.")
    # Personal-fit reasons (coloring / fit / taste) when we have a profile to judge.
    reasons.extend(style_reasons)

    # 7. Closet boost % — how much this raises wardrobe completeness
    #    Simple heuristic: gap fill = 5%, novel occasions = 3%, novel seasons = 2%
    boost_pct = 0.0
    if fills_gap:
        boost_pct += 5.0
    boost_pct += len(new_occasions) * 3.0
    boost_pct += len(new_seasons) * 2.0
    boost_pct = min(boost_pct, 20.0)

    # 8. Matched items shown in the UI: duplicates first (the honest warning),
    #    then the best genuine pairings. Both carry is_duplicate so the frontend
    #    renders "you own this" vs "pairs with this" distinctly.
    matched_summary: list[dict[str, Any]] = []
    for it in dupe_items[:5]:
        matched_summary.append(
            {
                "id": str(it.get("id", "")),
                "name": it.get("name", ""),
                "category": it.get("category", ""),
                "color": it.get("color", ""),
                "image_url": it.get("processed_image_url") or it.get("image_url"),
                "similarity_score": round(float(it.get("similarity_score", 0)), 3),
                "is_duplicate": True,
            }
        )
    matched_summary.extend(pairings[:6])

    # 8b. Honest one-liners surfaced in the UI.
    #     "completes N outfits" = distinct COMPLETE looks this unlocks from owned
    #     items (the real buy-signal), not just the count of items it pairs with.
    from app.core import outfit_builder

    dupe_count = len(dupe_items)
    completes_outfits, _capped = outfit_builder.count_completable_outfits(analysis, closet)

    # 9. Persist to DB
    record_id = str(uuid.uuid4())
    reasoning_text = " ".join(reasons) if reasons else "No specific matches found in your closet."

    sql = text("""
        INSERT INTO shopping_checks
            (id, user_id, image_url, item_analysis, matched_items,
             buy_score, buy_recommendation, closet_boost_pct, reasoning,
             input_type, source_url, created_at)
        VALUES
            (CAST(:id AS uuid), CAST(:uid AS uuid), :image_url,
             CAST(:analysis AS jsonb), CAST(:matched AS jsonb),
             :score, :rec, :boost, :reason,
             :input_type, :source_url, NOW())
    """)
    import json

    await session.execute(
        sql,
        {
            "id": record_id,
            "uid": user_id,
            "image_url": image_url,
            "analysis": json.dumps(analysis),
            "matched": json.dumps(matched_summary),
            "score": round(score, 1),
            "rec": recommendation,
            "boost": round(boost_pct, 1),
            "reason": reasoning_text,
            "input_type": input_type,
            "source_url": source_url,
        },
    )
    await session.commit()

    # Instrument repeat link-paste behaviour: the retention/viral signal. Cheap
    # count of how many URL/screenshot checks this user has now run.
    url_check_count = await _count_url_checks(session, user_id) if input_type != "photo" else 0

    # RAG-grounded natural-language verdict, layered ON TOP of the deterministic
    # score. Best-effort: the score is authoritative and the model may only explain
    # it from cited knowledge, so a failure here never blocks or skews the verdict.
    fani_take: dict[str, Any] | None = None
    try:
        fani_take = await _generate_grounded_take(
            session,
            analysis=analysis,
            score=score,
            dupe_count=dupe_count,
            pairing_names=[p["name"] for p in pairings[:5] if p.get("name")],
            compatible_count=compatible_count,
            fills_gap=fills_gap,
            new_occasions=new_occasions,
            new_seasons=new_seasons,
            category=category,
        )
    except Exception as exc:  # noqa: BLE001 — the take is never load-bearing
        logger.warning("shopping_take_generation_failed", error=str(exc))

    # Funnel: a verdict was produced. Records the shape of the result so we can
    # later correlate "what kind of verdict" with "did they act / paste again".
    await record_shopping_event(
        session,
        user_id,
        "check_created",
        check_id=record_id,
        metadata={
            "input_type": input_type,
            "recommendation": recommendation,
            "buy_score": round(score, 1),
            "dupe_count": dupe_count,
            "completes_outfits": completes_outfits,
            "has_source_url": bool(source_url),
        },
    )

    return {
        "check_id": record_id,
        "item_analysis": analysis,
        "matched_items": matched_summary,
        "buy_score": round(score, 1),
        # The verdict is shown as a RATING + COLOUR, never a buy/skip word.
        # 0–10 rating for display (82 → 8.2); 0–100 above stays canonical for the
        # breakdown bars and history. ``rating_color`` is green/amber/red.
        "buy_score_10": to_ten_point(score),
        "rating": to_ten_point(score),
        "rating_color": rating_color(score),
        # Kept for internal analytics only — NOT for display (it's a buy/skip band).
        "buy_recommendation": recommendation,
        "closet_boost_pct": round(boost_pct, 1),
        "score_breakdown": score_breakdown,
        # Max % each factor can contribute — lets the UI render "earned / max" bars
        # without hardcoding the weights. These are the EFFECTIVE weights actually
        # used (style_match is folded into closet factors when no profile exists),
        # so the bars always match the breakdown above.
        "score_weights": {k: round(v, 1) for k, v in weights_used.items()},
        # Personal-fit (coloring / fit / taste) sub-signal. null when the user has
        # no usable style profile — the UI can prompt them to complete onboarding.
        "style_match": round(style_match, 3) if style_match is not None else None,
        "reasoning": reasoning_text,
        "fani_take": fani_take,
        "image_url": image_url,
        "input_type": input_type,
        "source_url": source_url,
        "source_title": (product_meta or {}).get("title"),
        "source_brand": (product_meta or {}).get("brand"),
        "source_price": (product_meta or {}).get("price"),
        "source_site": (product_meta or {}).get("site_name"),
        "dupe_count": dupe_count,
        "completes_outfits": completes_outfits,
        "url_check_count": url_check_count,
    }


async def _count_url_checks(session: AsyncSession, user_id: str) -> int:
    """How many URL/screenshot-sourced checks this user has run (incl. the latest)."""
    sql = text("""
        SELECT COUNT(*) AS n FROM shopping_checks
        WHERE user_id = CAST(:uid AS uuid)
          AND input_type IN ('url', 'screenshot')
    """)
    result = await session.execute(sql, {"uid": user_id})
    row = result.mappings().first()
    return int(row["n"]) if row else 0


async def analyze_shopping_item_from_url(
    url: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Run the FANI buy/skip verdict against a pasted product URL.

    Pulls the product image from OG/JSON-LD metadata; if the page exposes none,
    falls back to a rendered screenshot (when a screenshot service is configured)
    and runs the same vision pipeline. No scraper infrastructure — one page fetch.
    """
    from app.core import product_url as product_url_mod
    from app.core.exceptions import BadRequestError
    from app.core.upload_service import persist_upload

    # 1. Try to read the page's OG/JSON-LD metadata. Big retailers (Abercrombie,
    #    Nike, Zara…) sit behind Akamai/Cloudflare bot managers that 403 any
    #    server-side fetch — that's expected, not a hard failure. We remember the
    #    page was blocked and degrade to the screenshot renderer below.
    meta: product_url_mod.ProductMetadata | None = None
    page_blocked = False
    try:
        meta = await product_url_mod.fetch_product_metadata(url)
    except BadRequestError as exc:
        # Re-raise true user errors (bad scheme, SSRF, malformed URL) immediately;
        # only "couldn't open / reach" failures are eligible for the screenshot path.
        msg = str(exc).lower()
        if "private" in msg or "http(s)" in msg or "valid url" in msg or "redirect" in msg:
            raise
        page_blocked = True
        logger.info("shopping_url_page_blocked", url=url[:120], detail=str(exc))

    source_url = meta.source_url if meta else url.strip()

    # 2. Prefer the author-curated product image when we could read the page.
    image: tuple[bytes, str] | None = None
    input_type = "url"
    if meta and meta.image_url:
        image = await product_url_mod.fetch_image_bytes(meta.image_url)

    # 3. Fall back to a rendered page screenshot through the same vision pipeline.
    #    This uses a real-browser render service (config:
    #    PRODUCT_SCREENSHOT_URL_TEMPLATE) which also gets past bot managers.
    if image is None:
        image = await product_url_mod.fetch_page_screenshot(source_url)
        if image is not None:
            input_type = "screenshot"

    if image is None:
        if page_blocked:
            raise BadRequestError(
                "That store blocks automated readers, so FANI couldn't open the "
                "page. Screenshot a photo of the item and upload it instead."
            )
        raise BadRequestError(
            "Couldn't pull a product image from that link. Try a direct product page, or snap a photo instead."
        )

    image_bytes, media_type = image

    # Persist the sourced image (best-effort — verdict still runs if storage fails).
    image_url: str | None = None
    try:
        image_url = await persist_upload(image_bytes, media_type, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("shopping_url_image_persist_failed", error=str(exc))

    # Carry a product-name hint (page title, else the URL slug) — this is what
    # lets vision pick the RIGHT garment out of a fully-styled product-page
    # screenshot instead of grabbing whichever item the model also wears.
    product_meta = meta.to_dict() if meta else {"source_url": source_url}
    if not product_meta.get("title"):
        title_hint = product_url_mod.product_name_hint_from_url(source_url)
        if title_hint:
            product_meta["title"] = title_hint

    return await analyze_shopping_item(
        image_bytes=image_bytes,
        media_type=media_type,
        user_id=user_id,
        session=session,
        image_url=image_url,
        input_type=input_type,
        source_url=source_url,
        product_meta=product_meta,
    )


def _outfit_note(anchor_name: str, items: list[dict[str, Any]], forgotten_ids: set[str], tier: str) -> str:
    """A short, deterministic stylist one-liner for a built outfit."""
    names = ", ".join(it["name"] for it in items if it.get("name"))
    anchor = anchor_name or "this piece"
    note = f"{tier} look — styles {anchor} with {names}." if names else f"{tier} look around {anchor}."
    forgotten = next((it["name"] for it in items if str(it.get("id", "")) in forgotten_ids and it.get("name")), None)
    if forgotten:
        note += f" Brings back your {forgotten} you haven't worn yet."
    return note


async def build_outfits_for_check(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Ask 2 — anchored outfit completion. Treat the checked item as the anchor and
    return the best complete outfits buildable from the user's own closet."""
    from app.core import outfit_builder

    fetch_sql = text("""
        SELECT id, image_url, item_analysis FROM shopping_checks
        WHERE id = CAST(:cid AS uuid) AND user_id = CAST(:uid AS uuid)
    """)
    res = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = res.mappings().first()
    if not row:
        return None

    import json as _json

    analysis = row["item_analysis"]
    if isinstance(analysis, str):
        analysis = _json.loads(analysis)

    closet = await _fetch_closet_for_compat(session, user_id)
    built = outfit_builder.build_outfits(analysis, closet)

    # Attach a stylist note to each outfit.
    for outfit in built["outfits"]:
        outfit["note"] = _outfit_note(
            analysis.get("name", ""),
            outfit["items"],
            set(outfit.get("forgotten_item_ids") or []),
            outfit["tier"],
        )

    # Ask 3: the buy-signal + actionable gap completers.
    completes_outfits, _capped = outfit_builder.count_completable_outfits(analysis, closet)
    gap_suggestions = outfit_builder.suggest_for_gaps(analysis, built["missing_roles"], closet)

    await record_shopping_event(
        session,
        user_id,
        "outfit_opened",
        check_id=check_id,
        metadata={
            "outfit_count": len(built["outfits"]),
            "completes_outfits": completes_outfits,
            "missing_roles": built["missing_roles"],
        },
    )

    return {
        "anchor": {
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "image_url": row.get("image_url"),
        },
        "outfits": built["outfits"],
        "missing_roles": built["missing_roles"],
        "completes_outfits": completes_outfits,
        "gap_suggestions": gap_suggestions,
    }


async def record_purchase_decision(
    check_id: str,
    user_id: str,
    bought: bool,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Record whether the user actually bought the item."""
    sql = text("""
        UPDATE shopping_checks
        SET purchase_decision = :bought,
            decision_at       = NOW()
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
        RETURNING id, buy_score, buy_recommendation, purchase_decision
    """)
    result = await session.execute(
        sql,
        {
            "bought": bought,
            "cid": check_id,
            "uid": user_id,
        },
    )
    row = result.mappings().first()
    if not row:
        return None
    await session.commit()
    await record_shopping_event(session, user_id, "verdict_acted", check_id=check_id, metadata={"bought": bought})
    return dict(row)


async def get_shopping_history(
    user_id: str,
    session: AsyncSession,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return the user's recent shopping checks, newest first."""
    sql = text("""
        SELECT id, image_url, item_analysis, matched_items, buy_score,
               buy_recommendation, closet_boost_pct, reasoning,
               input_type, source_url,
               purchase_decision, decision_at, created_at
        FROM shopping_checks
        WHERE user_id = CAST(:uid AS uuid)
        ORDER BY created_at DESC
        LIMIT :lim
    """)
    result = await session.execute(sql, {"uid": user_id, "lim": limit})
    rows = result.mappings().all()
    return [_shopping_check_row(dict(r)) for r in rows]


def _shopping_check_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize DB row for API responses (id → check_id, + 0–10 display score)."""
    out = dict(row)
    if "id" in out:
        out["check_id"] = str(out.pop("id"))
    if out.get("buy_score") is not None:
        out["buy_score_10"] = to_ten_point(out["buy_score"])
        out["rating"] = to_ten_point(out["buy_score"])
        out["rating_color"] = rating_color(out["buy_score"])
    return out


async def delete_shopping_check(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> tuple[bool, str | None]:
    """
    Delete a shopping check owned by the user.

    Returns (found, image_url) where image_url is set when a stored image
    should be cleaned up (best-effort).
    """
    fetch_sql = text("""
        SELECT image_url FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    result = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = result.mappings().first()
    if not row:
        return False, None

    delete_sql = text("""
        DELETE FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    await session.execute(delete_sql, {"cid": check_id, "uid": user_id})
    await session.commit()
    return True, row.get("image_url")


# ── Closet → Shopping: "Complete My Look" ────────────────────────────────────

_MATCH_SUGGESTIONS_SYSTEM = """You are FANI, a professional AI fashion stylist.
You help the user "Complete My Look" around ONE wardrobe item they selected.

You are given the selected item, the user's full closet inventory (each owned item is
numbered), and a [FASHION KNOWLEDGE] block of retrieved styling rules (each tagged
[SOURCE-N]). Your job:
1. Work out the complementary slots needed to build complete outfits around the selected item
   (e.g. for a blazer: a bottom, a shirt, footwear, maybe a belt).
2. For EACH slot, FIRST check the numbered closet inventory. If the user ALREADY OWNS an item
   that fills that slot well, reference it in "closet_pairings" by its number — DO NOT tell them
   to buy it.
3. ONLY recommend buying (in "suggestions") for slots the closet CANNOT fill from owned items.
   If the closet already completes the look, return an empty "suggestions" array.

GROUNDING RULES — these are mandatory and override any general fashion intuition:
- Reference owned items ONLY by the numbers given in the inventory. NEVER invent an item,
  a number, a brand, a color, or an attribute that is not in the provided data.
- Base every styling claim (color pairing, occasion fit, proportion, layering) on the
  [FASHION KNOWLEDGE] block. When a reason or styling_tip relies on a rule, cite it inline
  as [SOURCE-N] using the exact tag from the block.
- If the knowledge block does not cover a point, give conservative, widely-accepted advice
  and do NOT cite a source — never fabricate a citation, a price, or a specific brand.
- Do not assume occasions, seasons, or colors the data does not state. If unsure, omit the
  claim rather than guessing.

Prefer using what the user already owns. Be honest and grounded over impressive.

Return ONLY a valid json object with this exact structure:
{
  "outfit_potential": "high" | "medium" | "low",
  "styling_tip": "<1-2 sentence overall styling advice for this item>",
  "closet_pairings": [
    {
      "item_number": <integer index from the inventory list>,
      "role": "<the slot it fills, e.g. 'bottom', 'footwear', 'layer'>",
      "reason": "<why it works with the selected item — one short sentence>"
    }
  ],
  "suggestions": [
    {
      "category": "<specific item type to shop for, e.g. 'slim-fit chinos'>",
      "role": "<the slot this fills>",
      "reason": "<why this completes the look and why the closet can't already — one sentence>",
      "colors": ["<color1>", "<color2>"],
      "occasions": ["<occasion1>"],
      "priority": "high" | "medium" | "low",
      "price_range": "<budget hint e.g. '$30–$80'>"
    }
  ]
}
List closet_pairings first (best matches first). Provide at most 4 suggestions, only for genuine
gaps. No markdown fences, raw JSON only."""


async def get_closet_match_suggestions(
    closet_item_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Given a closet item, "Complete My Look": surface owned items that complete an outfit
    around it FIRST, and only suggest buying for slots the closet cannot fill.

    Flow:
    1. Fetch the selected closet item and its metadata.
    2. Fetch the user's full closet inventory (numbered) as matching context.
    3. Ask the AI to fill complementary slots from owned items first, and only recommend
       purchases for the remaining gaps.
    4. Resolve the AI's owned-item references back to real closet rows (id + image).
    """
    import json as _json

    # 1. Fetch selected closet item
    item_sql = text("""
        SELECT id, name, category, color, fabric, pattern, brand, season,
               occasion, tags, notes, image_url, processed_image_url
        FROM closet_items
        WHERE id = CAST(:iid AS uuid)
          AND user_id = CAST(:uid AS uuid)
          AND is_archived = false
    """)
    res = await session.execute(item_sql, {"iid": closet_item_id, "uid": user_id})
    item_row = res.mappings().first()
    if not item_row:
        return {}

    item = dict(item_row)

    # 2. Fetch full closet inventory (excluding the selected item) as matching context
    inv_sql = text("""
        SELECT id, name, category, color, occasion, image_url, processed_image_url
        FROM closet_items
        WHERE user_id = CAST(:uid AS uuid)
          AND is_archived = false
          AND id <> CAST(:iid AS uuid)
        ORDER BY created_at DESC
        LIMIT 60
    """)
    inv_res = await session.execute(inv_sql, {"uid": user_id, "iid": closet_item_id})
    inventory = [dict(r) for r in inv_res.mappings().all()]

    # 3. Build AI prompt — number each owned item so the AI can reference it reliably
    item_desc = (
        f"{item.get('name', 'Item')}: {item.get('category', '')}, {item.get('color', '')} "
        f"{item.get('fabric', '')} {item.get('pattern', '')}. "
        f"Occasions: {', '.join(item.get('occasion') or [])}. "
        f"Seasons: {', '.join(item.get('season') or [])}."
    )
    if inventory:
        inv_lines = "\n".join(
            f"[{i + 1}] {r.get('name', '')} — {r.get('category', '')}"
            f"{', ' + str(r['color']) if r.get('color') else ''}"
            f"{' (' + ', '.join(r.get('occasion') or []) + ')' if r.get('occasion') else ''}"
            for i, r in enumerate(inventory)
        )
    else:
        inv_lines = "(the closet is otherwise empty)"

    # RAG: ground the styling reasoning in retrieved fashion knowledge (color theory,
    # pairing rules, occasion guidance). Degrades to "" if unavailable.
    knowledge_text = ""
    try:
        rag_query = (
            f"How to complete an outfit around a {item.get('color', '')} "
            f"{item.get('category', '')}; what pieces pair well for "
            f"{', '.join(item.get('occasion') or ['everyday'])}"
        )
        knowledge_text = await get_fashion_context_for_prompt(session, rag_query, limit=3)
    except Exception as exc:  # noqa: BLE001 — RAG is best-effort context
        logger.warning("closet_match_rag_failed: %s", exc)

    # Wrap retrieved knowledge with the same cite-[SOURCE-N] contract the stylist
    # chat uses, so the model grounds its reasoning in retrieval instead of
    # free-associating. Empty string when retrieval found nothing.
    knowledge_block = (
        f"\n[FASHION KNOWLEDGE — cite [SOURCE-N] when referencing these rules]\n"
        f"{knowledge_text}\n[END FASHION KNOWLEDGE]\n"
        if knowledge_text
        else ""
    )

    user_msg = (
        f"Selected item to build a look around: {item_desc}\n\n"
        f"My closet inventory (owned items, numbered):\n{inv_lines}\n"
        f"{knowledge_block}\n"
        "Complete the look: pair owned items first, and only suggest buying for gaps the "
        "closet cannot fill. Ground every styling claim in the FASHION KNOWLEDGE above and "
        "cite [SOURCE-N]; reference owned items only by their inventory number. Do not invent "
        "items, brands, prices, or rules that are not provided."
    )

    # 4. Call AI — low temperature + JSON mode keeps the verdict deterministic and
    #    schema-clean, which (with the grounding rules) is what curbs hallucination.
    raw_response = await ai_service.chat(
        messages=[{"role": "user", "content": user_msg}],
        system_prompt=_MATCH_SUGGESTIONS_SYSTEM,
        use_json_mode=True,
        temperature=0.2,
    )

    # 5. Parse JSON
    data: dict[str, Any] = {}
    try:
        cleaned = raw_response.strip().strip("```json").strip("```").strip()
        data = _json.loads(cleaned)
    except Exception:
        logger.warning("Failed to parse closet-match AI response: %s", raw_response[:200])
        data = {
            "outfit_potential": "medium",
            "styling_tip": "This item has great pairing potential. Explore complementary pieces!",
            "closet_pairings": [],
            "suggestions": [],
        }

    # 6. Resolve AI owned-item references (1-based) back to real closet rows
    closet_pairings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for p in data.get("closet_pairings", []) or []:
        try:
            idx = int(p.get("item_number", 0)) - 1
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(inventory):
            continue
        row = inventory[idx]
        row_id = str(row.get("id", ""))
        if not row_id or row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        closet_pairings.append(
            {
                "id": row_id,
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "image_url": row.get("processed_image_url") or row.get("image_url"),
                "role": str(p.get("role", "")),
                "reason": str(p.get("reason", "")),
            }
        )

    # 7. Build response
    image_url = item.get("processed_image_url") or item.get("image_url")
    return {
        "closet_item": {
            "id": str(item["id"]),
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "color": item.get("color", ""),
            "image_url": image_url,
            "occasion": item.get("occasion") or [],
            "season": item.get("season") or [],
        },
        "closet_pairings": closet_pairings,
        "outfit_potential": data.get("outfit_potential", "medium"),
        "styling_tip": data.get("styling_tip", ""),
        "suggestions": data.get("suggestions", []),
        "grounded_in_knowledge": bool(knowledge_text),
    }


async def add_shopping_item_to_closet(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """
    Create a closet item from an already-analyzed shopping check record.
    Reuses the AI analysis data so no re-analysis is needed.
    """
    import json as _json

    # Fetch the shopping check
    fetch_sql = text("""
        SELECT id, image_url, item_analysis FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    res = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = res.mappings().first()
    if not row:
        return None

    analysis = row["item_analysis"]
    if isinstance(analysis, str):
        analysis = _json.loads(analysis)

    # Build embedding text
    item_text = item_to_embedding_text(
        {
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "fabric": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "season": analysis.get("season_tags") or [],
            "occasion": analysis.get("occasion_tags") or [],
            "tags": analysis.get("style_tags") or [],
            "notes": analysis.get("description", ""),
            "brand": analysis.get("brand", ""),
        }
    )
    embedding = await generate_text_embedding(item_text)
    emb_literal = vector_literal(embedding) if embedding else None

    new_id = str(uuid.uuid4())
    insert_sql = text(
        """
        INSERT INTO closet_items
            (id, user_id, name, category, color, fabric, pattern, brand,
             season, occasion, tags, notes, image_url, price,
             wear_count, is_archived, created_at
             {emb_col})
        VALUES
            (CAST(:id AS uuid), CAST(:uid AS uuid),
             :name, :category, :color, :fabric, :pattern, :brand,
             CAST(:season AS jsonb), CAST(:occasion AS jsonb), CAST(:tags AS jsonb),
             :notes, :image_url, :price,
             0, false, NOW()
             {emb_val})
        RETURNING id, name, category, color, image_url, price, created_at
    """.format(
            emb_col=", embedding" if emb_literal else "",
            emb_val=f", {emb_literal}" if emb_literal else "",
        )
    )

    import json

    result = await session.execute(
        insert_sql,
        {
            "id": new_id,
            "uid": user_id,
            "name": analysis.get("name") or analysis.get("category") or "Shopping Item",
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "fabric": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "brand": analysis.get("brand", ""),
            "season": json.dumps(analysis.get("season_tags") or []),
            "occasion": json.dumps(analysis.get("occasion_tags") or []),
            "tags": json.dumps(analysis.get("style_tags") or []),
            "notes": analysis.get("description", ""),
            "image_url": row.get("image_url"),
            # Backfill price from the scraped product metadata so cost-per-wear
            # works the moment the item is logged. None when no price was scraped.
            "price": parse_price_to_float(analysis.get("source_price")),
        },
    )
    await session.commit()
    await record_shopping_event(
        session,
        user_id,
        "added_to_closet",
        check_id=check_id,
        metadata={"closet_item_id": new_id},
    )
    created = result.mappings().first()
    return dict(created) if created else {"id": new_id}
