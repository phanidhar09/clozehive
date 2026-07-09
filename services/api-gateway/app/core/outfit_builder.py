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

# Combinatorial search bounds — evaluate enough combos to surface globally best
# looks, not just items that score highest against the anchor alone.
_MAX_COMBO_EVALUATIONS = 512
_MIN_CANDIDATES_PER_ROLE = 3
_MAX_CANDIDATES_PER_ROLE = 8
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


class ScoreCache:
    """Request-scoped memo for the O(n²)·combos inner loops.

    A single ``build_outfits`` call scores the same item against the same partners
    thousands of times (once per combo it appears in). Without memoization each of
    those calls re-parses both items' attributes and re-runs the styling math.
    This caches each item's parsed features (by object identity) and each pairwise
    result, so repeat work collapses to a dict lookup. Scoped per request — the
    item dicts it keys on stay alive for the request, so ``id()`` is stable.

    Pass one instance into ``build_outfits`` / ``count_completable_outfits`` (and
    use ``score`` directly) to also dedupe the same anchor-vs-closet scoring across
    several calls in one request, e.g. the shopping-check flow.
    """

    __slots__ = ("_features", "_pairs")

    def __init__(self) -> None:
        self._features: dict[int, compat.ItemFeatures] = {}
        self._pairs: dict[tuple[int, int], dict[str, Any]] = {}

    def features(self, item: dict[str, Any]) -> compat.ItemFeatures:
        key = id(item)
        feat = self._features.get(key)
        if feat is None:
            feat = compat.prepare(item)
            self._features[key] = feat
        return feat

    def score(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        key = (id(a), id(b))
        res = self._pairs.get(key)
        if res is None:
            res = compat.score_prepared(self.features(a), self.features(b))
            self._pairs[key] = res
        return res


def _item_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "name": item.get("name", ""),
        "category": item.get("category", ""),
        "color": item.get("color") or item.get("primary_color") or "",
        "pattern": item.get("pattern") or "",
        "image_url": item.get("processed_image_url") or item.get("image_url"),
        "role": compat.category_role(item.get("category")),
        "wear_count": int(item.get("wear_count") or 0),
    }


def _fit_pref_factor(owned_items: list[dict[str, Any]], fit_prefs: frozenset[str], fit_avoids: frozenset[str]) -> float:
    """Mean per-item fit-preference weight over an outfit's owned pieces.

    Each item contributes a soft multiplier from ``compat.fit_preference_weight``
    (>1 liked, <1 avoided, 1.0 neutral/unknown). Items with an unreadable fit stay
    neutral, so a look built entirely from unknown fits is unaffected (factor 1.0).
    """
    if not owned_items:
        return 1.0
    weights = [compat.fit_preference_weight(it.get("fit"), fit_prefs, fit_avoids)[0] for it in owned_items]
    return sum(weights) / len(weights)


def _mean_pairwise(items: list[dict[str, Any]], cache: ScoreCache) -> float:
    """Mean compatibility over every unordered pair — internal coherence."""
    pairs = list(combinations(items, 2))
    if not pairs:
        return 0.0
    total = sum(cache.score(a, b)["score"] for a, b in pairs)
    return total / len(pairs)


def _per_role_candidate_limit(num_fillable_roles: int) -> int:
    """How many candidates per required role while staying within the combo cap."""
    if num_fillable_roles <= 0:
        return 0
    per = max(_MIN_CANDIDATES_PER_ROLE, int(_MAX_COMBO_EVALUATIONS ** (1 / num_fillable_roles)))
    return min(_MAX_CANDIDATES_PER_ROLE, per)


def _overlap_ratio(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _select_diverse_outfits(outfits: list[dict[str, Any]], max_outfits: int) -> list[dict[str, Any]]:
    """Pick the highest-scoring looks with distinct core pieces when possible."""
    if not outfits or max_outfits <= 0:
        return []
    selected: list[dict[str, Any]] = []
    for outfit in outfits:
        if len(selected) >= max_outfits:
            break
        outfit_ids = frozenset(it["id"] for it in outfit["items"])
        if any(_overlap_ratio(outfit_ids, frozenset(it["id"] for it in s["items"])) > 0.66 for s in selected):
            continue
        selected.append(outfit)
    if len(selected) < max_outfits:
        for outfit in outfits:
            if outfit in selected:
                continue
            selected.append(outfit)
            if len(selected) >= max_outfits:
                break
    return selected[:max_outfits]


def _add_best_optional_layers(
    items: list[dict[str, Any]],
    plan: dict[str, tuple[str, ...]],
    buckets: dict[str, list[tuple[dict[str, Any], float]]],
    cache: ScoreCache,
) -> list[dict[str, Any]]:
    """Greedily add optional roles that raise the outfit's mean pairwise score."""
    result = list(items)
    for opt_role in plan["optional"]:
        best: tuple[dict[str, Any], float] | None = None
        for cand, _anchor_score in buckets.get(opt_role, []):
            trial = result + [cand]
            score = _mean_pairwise(trial, cache)
            if score >= _WEARABLE and (best is None or score > best[1]):
                best = (cand, score)
        if best is not None:
            result.append(best[0])
    return result


def build_outfits(
    anchor: dict[str, Any],
    closet: list[dict[str, Any]],
    *,
    max_outfits: int = _MAX_OUTFITS,
    cache: ScoreCache | None = None,
    fit_prefs: frozenset[str] = frozenset(),
    fit_avoids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Build the top complete outfits around ``anchor``.

    Returns ``{anchor_role, outfits, missing_roles}`` where each outfit is
    ``{score, tier, items, missing_roles, forgotten_item_ids, note_seed}``.
    ``missing_roles`` (top level) are required roles the closet can't fill at all.

    Pass a shared ``cache`` to reuse anchor-vs-closet scoring already done by a
    sibling call (e.g. an explicit pairing loop) on the same anchor and items.

    ``fit_prefs`` / ``fit_avoids`` are the user's declared fit taste (lowercased
    tokens). When supplied they apply a soft, bounded re-rank toward looks built
    from liked fits — a tie-breaker, never a filter (see ``_fit_pref_factor``).
    """
    anchor_role = compat.category_role(anchor.get("category"))
    plan = _ROLE_PLAN.get(anchor_role, _ROLE_PLAN["top"])
    cache = cache or ScoreCache()

    # Bucket closet items by role, scored against the anchor.
    buckets: dict[str, list[tuple[dict[str, Any], float]]] = {}
    for item in closet:
        res = cache.score(anchor, item)
        if not res["role_compatible"] or res["score"] < _CANDIDATE_FLOOR:
            continue
        role = compat.category_role(item.get("category"))
        buckets.setdefault(role, []).append((item, res["score"]))
    for role in buckets:
        buckets[role].sort(key=lambda t: t[1], reverse=True)

    # Required roles the closet cannot fill — these are the gaps.
    missing_required = [r for r in plan["required"] if not buckets.get(r)]
    fillable_required = [r for r in plan["required"] if buckets.get(r)]

    # Candidate sets for the cartesian product — top-N per role, bounded so the
    # full product stays ≤ _MAX_COMBO_EVALUATIONS. Scoring uses mean pairwise
    # coherence so a piece that pairs better with shoes than with the anchor alone
    # can still win.
    per_role = _per_role_candidate_limit(len(fillable_required))
    candidate_lists = [[item for item, _ in buckets[r][:per_role]] for r in fillable_required]

    outfits: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()

    combos = list(product(*candidate_lists)) if candidate_lists else [()]
    for combo in combos:
        items = _add_best_optional_layers([anchor, *combo], plan, buckets, cache)

        owned_items = [it for it in items if it is not anchor]
        key = frozenset(str(it.get("id", "")) for it in owned_items)
        if not key or key in seen:
            continue
        seen.add(key)

        score = _mean_pairwise(items, cache)
        # Soft user-taste tilt: average each owned piece's fit-preference weight
        # and apply it as a bounded multiplier. Re-ranks toward liked fits; the
        # clamp keeps scores inside the tier thresholds and it can never zero an
        # outfit out. The anchor is user-chosen, so it's exempt from demotion.
        if fit_prefs or fit_avoids:
            score = min(1.0, score * _fit_pref_factor(owned_items, fit_prefs, fit_avoids))
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
        "outfits": _select_diverse_outfits(outfits, max_outfits),
        "missing_roles": missing_required,
    }


def best_pairing_ids(build_result: dict[str, Any], *, max_ids: int = 12) -> set[str]:
    """IDs from the highest-scoring complete outfits — for ranking individual pairings."""
    ids: list[str] = []
    for outfit in build_result.get("outfits", []):
        for item in outfit.get("items", []):
            iid = str(item.get("id", ""))
            if iid and iid not in ids:
                ids.append(iid)
            if len(ids) >= max_ids:
                return set(ids)
    return set(ids)


def best_pairings_from_build(
    anchor: dict[str, Any],
    build_result: dict[str, Any],
    *,
    max_pairings: int = 6,
) -> list[dict[str, Any]]:
    """Extract the best complementary items from top complete outfits."""
    pairings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for outfit in build_result.get("outfits", []):
        for item_view in outfit["items"]:
            iid = str(item_view.get("id", ""))
            if not iid or iid in seen_ids:
                continue
            seen_ids.add(iid)
            owned = {
                "id": iid,
                "name": item_view.get("name", ""),
                "category": item_view.get("category", ""),
                "color": item_view.get("color", ""),
                "primary_color": item_view.get("color", ""),
                "pattern": item_view.get("pattern", ""),
            }
            compat_result = compat.score_compatibility(anchor, owned)
            reasons = compat_result.get("reasons") or []
            pairings.append(
                {
                    "id": iid,
                    "name": item_view.get("name", ""),
                    "category": item_view.get("category", ""),
                    "image_url": item_view.get("image_url"),
                    "role": item_view.get("role", ""),
                    "reason": reasons[0] if reasons else "Best match from your highest-scoring complete look.",
                    "similarity_score": compat_result["score"],
                    "outfit_score": outfit.get("score"),
                }
            )
            if len(pairings) >= max_pairings:
                return pairings
    return pairings


def suggest_complementary_pairings(
    selected: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
    *,
    max_pairings: int = 6,
) -> list[dict[str, Any]]:
    """Best closet items to complement a partial outfit by mean pairwise compatibility."""
    if not selected or not remaining:
        return []

    cache = ScoreCache()
    scored: list[tuple[dict[str, Any], float, list[str]]] = []
    for item in remaining:
        hits: list[tuple[float, list[str]]] = []
        for sel in selected:
            res = cache.score(sel, item)
            if res["pairs"]:
                hits.append((res["score"], res["reasons"]))
        if not hits:
            continue
        mean_score = sum(s for s, _ in hits) / len(hits)
        reasons = [r for _, rs in hits for r in rs]
        scored.append((item, mean_score, reasons))

    scored.sort(key=lambda t: t[1], reverse=True)
    return [
        {
            "id": str(item.get("id", "")),
            "reason": reasons[0] if reasons else "Pairs well with your selected pieces.",
        }
        for item, _, reasons in scored[:max_pairings]
    ]


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


def _candidates_by_role(
    anchor: dict[str, Any], closet: list[dict[str, Any]], cache: ScoreCache | None = None
) -> dict[str, list[dict[str, Any]]]:
    cache = cache or ScoreCache()
    out: dict[str, list[dict[str, Any]]] = {}
    for item in closet:
        res = cache.score(anchor, item)
        if res["role_compatible"] and res["score"] >= _CANDIDATE_FLOOR:
            out.setdefault(compat.category_role(item.get("category")), []).append(item)
    return out


def count_completable_outfits(
    anchor: dict[str, Any], closet: list[dict[str, Any]], *, cache: ScoreCache | None = None
) -> tuple[int, bool]:
    """How many DISTINCT complete outfits this anchor unlocks from owned items —
    the "buying this completes N outfits" buy-signal. Counts coherent combinations
    (one item per required role, all pieces pairing with each other), capped.

    Returns ``(count, capped)``. Pass a shared ``cache`` to reuse anchor-vs-closet
    scoring from a sibling call on the same anchor and items.
    """
    anchor_role = compat.category_role(anchor.get("category"))
    plan = _ROLE_PLAN.get(anchor_role, _ROLE_PLAN["top"])
    cache = cache or ScoreCache()
    buckets = _candidates_by_role(anchor, closet, cache)

    required = plan["required"]
    if any(not buckets.get(r) for r in required):
        return (0, False)  # can't complete a full look

    # Bound the per-role fan-out so the product stays sane on large closets.
    lists = [buckets[r][:8] for r in required]

    count = 0
    capped = False
    for combo in product(*lists):
        items = [anchor, *combo]
        if _mean_pairwise(items, cache) >= _WEARABLE:
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


def suggest_for_gaps(
    anchor: dict[str, Any], missing_roles: list[str], closet: list[dict[str, Any]]
) -> list[dict[str, Any]]:
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
