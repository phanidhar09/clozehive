"""Anchored outfit completion — "build the best looks I could wear with this".

Given a pasted item as a FIXED anchor, search the closet for the best complete
outfits built around it (one item per complementary role). Pure and deterministic
— it reuses the compatibility engine for every pairwise judgement, so it's cheap
to run on demand and easy to unit-test (no AI call on the hot path; an AI stylist
note can be layered on top by the caller).

An outfit is scored by the mean pairwise compatibility across all its pieces
(anchor included), so it rewards looks that cohere internally, not just items that
each happen to match the anchor. Missing required roles are returned as gaps —
that's the seam Ask 3 (gap detection / "completes N outfits") plugs into.
"""

from __future__ import annotations

from itertools import combinations, product
from typing import Any

from app.core import outfit_compatibility as compat

# Which roles a complete outfit needs, by the anchor's own role.
_ROLE_PLAN: dict[str, dict[str, tuple[str, ...]]] = {
    "top": {"required": ("bottom", "shoe"), "optional": ("layer", "accessory")},
    "bottom": {"required": ("top", "shoe"), "optional": ("layer", "accessory")},
    "onepiece": {"required": ("shoe",), "optional": ("layer", "accessory")},
    "layer": {"required": ("top", "bottom", "shoe"), "optional": ("accessory",)},
    "shoe": {"required": ("top", "bottom"), "optional": ("layer", "accessory")},
    "accessory": {"required": ("top", "bottom", "shoe"), "optional": ("layer",)},
    "other": {"required": ("top", "bottom", "shoe"), "optional": ("layer", "accessory")},
}

# Per required/optional role, how many top candidates to consider. Keeps the
# combinatorial search bounded (≤ 3^3 = 27 base combos).
_CANDIDATES_PER_ROLE = 3
# A closet item must clear this anchor-compatibility floor to be a candidate.
_CANDIDATE_FLOOR = 0.55
_MAX_OUTFITS = 3

# 5-tier rating from an outfit's mean pairwise compatibility.
_TIERS = (
    (0.85, "Perfect"),
    (0.75, "Great"),
    (0.66, "Solid"),
    (0.58, "Wearable"),
    (0.0, "Risky"),
)


def rating_tier(score: float) -> str:
    for threshold, label in _TIERS:
        if score >= threshold:
            return label
    return "Risky"


def _item_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "name": item.get("name", ""),
        "category": item.get("category", ""),
        "color": item.get("color") or item.get("primary_color") or "",
        "image_url": item.get("processed_image_url") or item.get("image_url"),
        "role": compat.category_role(item.get("category")),
        "wear_count": int(item.get("wear_count") or 0),
    }


def _mean_pairwise(items: list[dict[str, Any]]) -> float:
    """Mean compatibility over every unordered pair — internal coherence."""
    pairs = list(combinations(items, 2))
    if not pairs:
        return 0.0
    total = sum(compat.score_compatibility(a, b)["score"] for a, b in pairs)
    return total / len(pairs)


def build_outfits(
    anchor: dict[str, Any],
    closet: list[dict[str, Any]],
    *,
    max_outfits: int = _MAX_OUTFITS,
) -> dict[str, Any]:
    """Build the top complete outfits around ``anchor``.

    Returns ``{anchor_role, outfits, missing_roles}`` where each outfit is
    ``{score, tier, items, missing_roles, forgotten_item_ids, note_seed}``.
    ``missing_roles`` (top level) are required roles the closet can't fill at all.
    """
    anchor_role = compat.category_role(anchor.get("category"))
    plan = _ROLE_PLAN.get(anchor_role, _ROLE_PLAN["top"])

    # Bucket closet items by role, scored against the anchor.
    buckets: dict[str, list[tuple[dict[str, Any], float]]] = {}
    for item in closet:
        res = compat.score_compatibility(anchor, item)
        if not res["role_compatible"] or res["score"] < _CANDIDATE_FLOOR:
            continue
        role = compat.category_role(item.get("category"))
        buckets.setdefault(role, []).append((item, res["score"]))
    for role in buckets:
        buckets[role].sort(key=lambda t: t[1], reverse=True)

    # Required roles the closet cannot fill — these are the gaps.
    missing_required = [r for r in plan["required"] if not buckets.get(r)]
    fillable_required = [r for r in plan["required"] if buckets.get(r)]

    # Candidate sets for the cartesian product (top N per fillable required role).
    candidate_lists = [
        [item for item, _ in buckets[r][:_CANDIDATES_PER_ROLE]] for r in fillable_required
    ]

    outfits: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()

    combos = list(product(*candidate_lists)) if candidate_lists else [()]
    for combo in combos:
        items = [anchor, *combo]

        # Greedily add optional roles that genuinely cohere with the look so far.
        for opt_role in plan["optional"]:
            best: tuple[dict[str, Any], float] | None = None
            for cand, _anchor_score in buckets.get(opt_role, []):
                coherence = sum(
                    compat.score_compatibility(cand, existing)["score"] for existing in items
                ) / len(items)
                if coherence >= compat.PAIR_THRESHOLD and (best is None or coherence > best[1]):
                    best = (cand, coherence)
            if best is not None:
                items.append(best[0])

        owned_items = [it for it in items if it is not anchor]
        key = frozenset(str(it.get("id", "")) for it in owned_items)
        if not key or key in seen:
            continue
        seen.add(key)

        score = _mean_pairwise(items)
        forgotten = [str(it.get("id", "")) for it in owned_items if int(it.get("wear_count") or 0) == 0]
        outfits.append(
            {
                "score": round(score, 3),
                "tier": rating_tier(score),
                "items": [_item_view(it) for it in owned_items],
                "missing_roles": list(missing_required),
                "forgotten_item_ids": forgotten,
            }
        )

    outfits.sort(key=lambda o: o["score"], reverse=True)
    return {
        "anchor_role": anchor_role,
        "outfits": outfits[:max_outfits],
        "missing_roles": missing_required,
    }


# ── Ask 3: "completes N outfits" + gap suggestions ────────────────────────────

# Cap the headline count so the buy-signal stays honest and bounded.
_COMPLETES_CAP = 25
# A complete outfit must clear this internal-coherence bar to count.
_WEARABLE = 0.58

# Roles the user actually shops for, with a concrete shoppable label.
_ROLE_SHOP_LABEL = {
    "top": "a top",
    "bottom": "bottoms (chinos, jeans, trousers)",
    "shoe": "shoes",
    "layer": "a jacket or layer",
    "accessory": "an accessory (belt, watch)",
    "onepiece": "a dress",
}


def _candidates_by_role(anchor: dict[str, Any], closet: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for item in closet:
        res = compat.score_compatibility(anchor, item)
        if res["role_compatible"] and res["score"] >= _CANDIDATE_FLOOR:
            out.setdefault(compat.category_role(item.get("category")), []).append(item)
    return out


def count_completable_outfits(anchor: dict[str, Any], closet: list[dict[str, Any]]) -> tuple[int, bool]:
    """How many DISTINCT complete outfits this anchor unlocks from owned items —
    the "buying this completes N outfits" buy-signal. Counts coherent combinations
    (one item per required role, all pieces pairing with each other), capped.

    Returns ``(count, capped)``.
    """
    anchor_role = compat.category_role(anchor.get("category"))
    plan = _ROLE_PLAN.get(anchor_role, _ROLE_PLAN["top"])
    buckets = _candidates_by_role(anchor, closet)

    required = plan["required"]
    if any(not buckets.get(r) for r in required):
        return (0, False)  # can't complete a full look

    # Bound the per-role fan-out so the product stays sane on large closets.
    lists = [buckets[r][:8] for r in required]

    count = 0
    capped = False
    for combo in product(*lists):
        items = [anchor, *combo]
        if _mean_pairwise(items) >= _WEARABLE:
            count += 1
            if count >= _COMPLETES_CAP:
                capped = True
                break
    return (count, capped)


def _suggested_colors(anchor: dict[str, Any]) -> list[str]:
    """Colours for a gap item that will reliably pair with the anchor. Neutrals
    always work; for a chromatic anchor we add its complement family."""
    base = ["white", "black", "tan", "navy"]
    kind, hue = compat.color_profile(anchor.get("primary_color") or anchor.get("color"))
    if kind == "chromatic" and hue is not None:
        comp = (hue + 180) % 360
        family = min(compat._CHROMATIC_HUES.items(), key=lambda kv: abs(((kv[1] - comp + 180) % 360) - 180))
        base.insert(0, family[0])
    return base[:3]


def suggest_for_gaps(anchor: dict[str, Any], missing_roles: list[str], closet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each missing required role, a concrete, attribute-rich completer
    suggestion + how many outfits it would unlock."""
    if not missing_roles:
        return []
    fl = compat.formality_level(anchor)
    formality = "casual" if fl < 1.6 else ("smart casual" if fl < 2.7 else "dressy")
    buckets = _candidates_by_role(anchor, closet)

    suggestions = []
    for role in missing_roles:
        # How many outfits this single addition would unlock: the product of the
        # OTHER required roles already covered (this gap is the only blocker).
        anchor_role = compat.category_role(anchor.get("category"))
        other_required = [r for r in _ROLE_PLAN.get(anchor_role, _ROLE_PLAN["top"])["required"] if r != role]
        unlocked = 1
        for r in other_required:
            unlocked *= max(len(buckets.get(r, [])), 1)
        suggestions.append(
            {
                "role": role,
                "shop_for": _ROLE_SHOP_LABEL.get(role, role),
                "suggested_colors": _suggested_colors(anchor),
                "formality": formality,
                "completes_outfits": min(unlocked, _COMPLETES_CAP),
                "reason": (
                    f"You have no {role} that works with this — add one in a "
                    f"{formality} {', '.join(_suggested_colors(anchor)[:2])} and it "
                    f"completes {min(unlocked, _COMPLETES_CAP)} outfit(s) from items you own."
                ),
            }
        )
    return suggestions
