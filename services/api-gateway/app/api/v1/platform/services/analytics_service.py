"""AnalyticsService for closet insights."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services.purchase_gap_service import detect_and_save_gaps
from app.api.v1.platform.schemas.analytics import (
    CategoryCoverageItem,
    CategoryStats,
    ClosetAnalyticsResponse,
    ClosetSummary,
    ColorStats,
    CostPerWearItem,
    DigestItem,
    ForgottenGem,
    OutfitReadiness,
    PurchaseGapInsight,
    VersatilityItem,
    WardrobeValueInsights,
    WeeklyDigest,
)
from app.models.closet import ClosetItem, Outfit, WearEvent

# An item unworn for this long is a "forgotten gem" candidate to resurface.
_FORGOTTEN_DAYS = 60
# Window for the "active" utilization rate.
_ACTIVE_WINDOW_DAYS = 90
# The weekly recap covers the trailing 7 days.
_DIGEST_WINDOW_DAYS = 7


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_closet_analytics(self, user_id: UUID) -> ClosetAnalyticsResponse:
        stmt = select(ClosetItem).where(ClosetItem.user_id == user_id)
        result = await self.session.execute(stmt)
        items = result.scalars().all()

        summary = self._compute_summary(items)
        category_coverage = self._compute_category_coverage(items)
        color_stats = self._compute_color_stats(items)
        category_stats = self._compute_category_stats(items)
        outfit_readiness = self._compute_outfit_readiness(items)
        value_insights = await self._compute_value_insights(user_id, items)

        # ── RAG: semantic purchase-gap detection ──────────────────────────────
        purchase_gap_insights: list[PurchaseGapInsight] = []
        try:
            closet_dicts = [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "category": item.category,
                    "color": item.color or "",
                    "occasion": item.occasion or [],
                }
                for item in items
            ]
            gap_records = await detect_and_save_gaps(
                self.session,
                str(user_id),
                closet_dicts,
            )
            purchase_gap_insights = [
                PurchaseGapInsight(
                    gap_type=g.gap_type,
                    missing_category=g.missing_category,
                    reason=g.reason or "",
                    priority_score=float(g.priority_score or 0),
                    suggested_attributes=g.suggested_attributes,
                )
                for g in gap_records
            ]
        except Exception:
            pass  # Gap analysis is best-effort; never break the analytics response

        return ClosetAnalyticsResponse(
            summary=summary,
            category_coverage=category_coverage,
            color_stats=color_stats,
            category_stats=category_stats,
            outfit_readiness=outfit_readiness,
            usage_insights=None,
            value_insights=value_insights,
            purchase_gap_insights=purchase_gap_insights,
        )

    def _compute_summary(self, items: Sequence[ClosetItem]) -> ClosetSummary:
        if not items:
            return ClosetSummary(
                total_items=0,
                strongest_category=None,
                most_common_color=None,
                best_covered_occasion=None,
            )

        total = len(items)
        categories = [i.category for i in items]
        strongest_category = Counter(categories).most_common(1)[0][0] if categories else None

        colors = [c.split("/")[0].strip() for i in items if i.color for c in [i.color]]
        most_common_color = Counter(colors).most_common(1)[0][0] if colors else None

        occasions = []
        for item in items:
            if item.occasion:
                if isinstance(item.occasion, list):
                    occasions.extend(item.occasion)
                elif isinstance(item.occasion, str):
                    occasions.append(item.occasion)
        best_covered_occasion = Counter(occasions).most_common(1)[0][0] if occasions else None

        return ClosetSummary(
            total_items=total,
            strongest_category=strongest_category,
            most_common_color=most_common_color,
            best_covered_occasion=best_covered_occasion,
        )

    def _compute_category_coverage(self, items: Sequence[ClosetItem]) -> list[CategoryCoverageItem]:
        category_counts = Counter(i.category for i in items)
        recommendations = {
            "tops": 6,
            "bottoms": 4,
            "shoes": 2,
            "outerwear": 2,
            "dresses": 2,
            "accessories": 4,
            "inners": 4,
            "special_occasion": 1,
        }

        result = []
        for category, recommended in recommendations.items():
            count = category_counts.get(category, 0)
            if count >= recommended:
                status = "good"
            elif count > 0:
                status = "low"
            else:
                status = "missing"

            result.append(
                CategoryCoverageItem(
                    category=category,
                    count=count,
                    recommended_minimum=recommended,
                    status=status,
                )
            )

        return sorted(result, key=lambda x: x.count, reverse=True)

    def _compute_color_stats(self, items: Sequence[ClosetItem]) -> list[ColorStats]:
        if not items:
            return []

        colors = []
        for item in items:
            if item.color:
                main_color = item.color.split("/")[0].strip()
                colors.append(main_color)

        if not colors:
            return []

        total = len(items)
        color_counts = Counter(colors)
        result = []

        for color, count in color_counts.most_common(6):
            result.append(
                ColorStats(
                    color=color,
                    count=count,
                    percentage=round((count / total) * 100, 1),
                )
            )

        return result

    def _compute_category_stats(self, items: Sequence[ClosetItem]) -> list[CategoryStats]:
        if not items:
            return []

        total = len(items)
        category_counts = Counter(i.category for i in items)
        result = []

        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            result.append(
                CategoryStats(
                    category=category.capitalize(),
                    count=count,
                    percentage=round((count / total) * 100, 1),
                )
            )

        return result

    def _compute_outfit_readiness(self, items: Sequence[ClosetItem]) -> OutfitReadiness:
        if not items:
            return OutfitReadiness(
                estimated_outfits=0,
                best_covered_occasions=[],
                weakest_covered_occasions=[],
            )

        occasions = []
        for item in items:
            if item.occasion:
                if isinstance(item.occasion, list):
                    occasions.extend(item.occasion)
                elif isinstance(item.occasion, str):
                    occasions.append(item.occasion)

        occasion_counts = Counter(occasions)
        best_covered = [o[0] for o in occasion_counts.most_common(3)]
        weakest_covered = [o[0] for o in occasion_counts.most_common()[-3:] if o[1] > 0]

        tops = sum(1 for i in items if i.category in ["tops", "dresses"])
        bottoms = sum(1 for i in items if i.category == "bottoms")
        shoes = sum(1 for i in items if i.category == "shoes")

        estimated_outfits = min(tops, bottoms, shoes) if tops and bottoms and shoes else tops

        return OutfitReadiness(
            estimated_outfits=estimated_outfits,
            best_covered_occasions=best_covered,
            weakest_covered_occasions=weakest_covered,
        )

    async def _compute_value_insights(self, user_id: UUID, items: Sequence[ClosetItem]) -> WardrobeValueInsights:
        """Cost-per-wear, utilization, forgotten gems, and versatility.

        Built from price + the wear rollup (wear_count / last_worn) on each item,
        plus saved-outfit membership for versatility. Archived items are excluded
        so the numbers reflect the wardrobe the user actually styles from.
        """
        active = [i for i in items if not i.is_archived]
        if not active:
            return WardrobeValueInsights(
                items_priced=0,
                total_value=0.0,
                value_worn=0.0,
                value_unworn=0.0,
                utilization_rate=0.0,
                active_rate_90d=0.0,
                avg_cost_per_wear=None,
            )

        today = date.today()
        active_cutoff = today - timedelta(days=_ACTIVE_WINDOW_DAYS)
        forgotten_cutoff = today - timedelta(days=_FORGOTTEN_DAYS)

        # ── Utilization (counter-based, works without prices) ─────────────────
        worn_ever = sum(1 for i in active if (i.wear_count or 0) > 0)
        worn_90d = sum(1 for i in active if i.last_worn and i.last_worn >= active_cutoff)
        total = len(active)
        utilization_rate = round(worn_ever / total * 100, 1)
        active_rate_90d = round(worn_90d / total * 100, 1)

        # ── Value math (needs prices) ─────────────────────────────────────────
        # Pair each priced item with its price as a float so the value math is
        # None-safe (the filter guarantees price is set).
        priced = [(i, float(i.price)) for i in active if i.price is not None]
        total_value = sum(price for _, price in priced)
        value_worn = sum(price for i, price in priced if (i.wear_count or 0) > 0)
        value_unworn = round(total_value - value_worn, 2)

        # ── Cost-per-wear, ranked (priced + actually worn) ────────────────────
        cpw: list[CostPerWearItem] = []
        for i, price in priced:
            wc = i.wear_count or 0
            if wc <= 0:
                continue  # cost-per-wear is meaningless before the first wear
            cpw.append(
                CostPerWearItem(
                    item_id=str(i.id),
                    name=i.name,
                    category=i.category,
                    price=price,
                    wear_count=wc,
                    cost_per_wear=round(price / wc, 2),
                )
            )
        cpw.sort(key=lambda c: c.cost_per_wear)
        best_value = cpw[:5]
        worst_value = list(reversed(cpw[-5:])) if cpw else []
        avg_cost_per_wear = round(sum(c.cost_per_wear for c in cpw) / len(cpw), 2) if cpw else None

        # ── Forgotten gems: never worn, or unworn past the threshold ──────────
        gems: list[ForgottenGem] = []
        for i in active:
            wc = i.wear_count or 0
            if wc == 0:
                gems.append(
                    ForgottenGem(
                        item_id=str(i.id),
                        name=i.name,
                        category=i.category,
                        wear_count=0,
                        last_worn=None,
                        days_since_worn=None,
                    )
                )
            elif i.last_worn and i.last_worn <= forgotten_cutoff:
                gems.append(
                    ForgottenGem(
                        item_id=str(i.id),
                        name=i.name,
                        category=i.category,
                        wear_count=wc,
                        last_worn=i.last_worn.isoformat(),
                        days_since_worn=(today - i.last_worn).days,
                    )
                )
        # Surface the most-neglected first: never-worn (None) before long-unworn,
        # then longest gap. Oldest items (by created_at) break ties among never-worn.
        gems.sort(key=lambda g: (g.days_since_worn is not None, -(g.days_since_worn or 0)))
        forgotten_gems = gems[:8]

        # ── Versatility: how many saved outfits each item appears in ──────────
        most_versatile = await self._compute_versatility(user_id, active)

        return WardrobeValueInsights(
            items_priced=len(priced),
            total_value=round(total_value, 2),
            value_worn=round(value_worn, 2),
            value_unworn=value_unworn,
            utilization_rate=utilization_rate,
            active_rate_90d=active_rate_90d,
            avg_cost_per_wear=avg_cost_per_wear,
            best_value_items=best_value,
            worst_value_items=worst_value,
            forgotten_gems=forgotten_gems,
            most_versatile=most_versatile,
        )

    async def _compute_versatility(self, user_id: UUID, items: Sequence[ClosetItem]) -> list[VersatilityItem]:
        """Count saved-outfit membership per item (Outfit.item_ids holds str ids)."""
        result = await self.session.execute(select(Outfit.item_ids).where(Outfit.user_id == user_id))
        counts: Counter[str] = Counter()
        for (item_ids,) in result.all():
            for raw in item_ids or []:
                counts[str(raw)] += 1
        if not counts:
            return []

        by_id = {str(i.id): i for i in items}
        ranked: list[VersatilityItem] = []
        for item_id, count in counts.most_common():
            item = by_id.get(item_id)
            if item is None:  # outfit references a deleted/archived item
                continue
            ranked.append(
                VersatilityItem(
                    item_id=item_id,
                    name=item.name,
                    category=item.category,
                    outfit_count=count,
                )
            )
            if len(ranked) >= 5:
                break
        return ranked

    # ── Weekly digest ──────────────────────────────────────────────────────────

    async def get_weekly_digest(self, user_id: UUID, today: date | None = None) -> WeeklyDigest:
        """'Your Week in Style' — the trailing-7-day recap.

        Reads wear_events for the window (distinct items, counts, the week's
        most-worn) and the closet rollup for context (new arrivals, utilization,
        a forgotten gem to revive). Deterministic so it can render on every
        dashboard load without an LLM call.
        """
        today = today or date.today()
        window_start = today - timedelta(days=_DIGEST_WINDOW_DAYS - 1)

        # Active wardrobe, keyed by id for cheap lookups.
        items = list(
            (
                await self.session.execute(
                    select(ClosetItem).where(
                        ClosetItem.user_id == user_id,
                        ClosetItem.is_archived == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {i.id: i for i in items}

        # ── This week's wears (from the event history) ────────────────────────
        wear_rows = (
            await self.session.execute(
                select(WearEvent.item_id, func.count())
                .where(
                    WearEvent.user_id == user_id,
                    WearEvent.worn_on >= window_start,
                    WearEvent.worn_on <= today,
                )
                .group_by(WearEvent.item_id)
            )
        ).all()
        wears_logged = sum(int(c) for _, c in wear_rows)
        items_worn = len(wear_rows)

        most_worn: DigestItem | None = None
        if wear_rows:
            top_item_id, top_count = max(wear_rows, key=lambda r: int(r[1]))
            item = by_id.get(top_item_id)
            if item is not None:
                most_worn = DigestItem(
                    item_id=str(item.id),
                    name=item.name,
                    category=item.category,
                    detail=f"worn {int(top_count)}× this week",
                )

        # ── Best value among items worn this week (lowest cost-per-wear) ──────
        best_value: DigestItem | None = None
        worn_ids = {iid for iid, _ in wear_rows}
        priced_worn = [
            by_id[iid]
            for iid in worn_ids
            if iid in by_id and by_id[iid].price is not None and (by_id[iid].wear_count or 0) > 0
        ]
        if priced_worn:
            cheapest = min(priced_worn, key=lambda i: float(i.price or 0) / (i.wear_count or 1))
            cpw = round(float(cheapest.price or 0) / (cheapest.wear_count or 1), 2)
            best_value = DigestItem(
                item_id=str(cheapest.id),
                name=cheapest.name,
                category=cheapest.category,
                detail=f"${cpw:g} per wear",
            )

        # ── New arrivals this week ────────────────────────────────────────────
        new_items = len([i for i in items if i.created_at and i.created_at.date() >= window_start])

        # ── One forgotten gem to revive (worn before, quiet ≥ threshold) ──────
        forgotten_cutoff = today - timedelta(days=_FORGOTTEN_DAYS)
        # Pair each candidate with its (non-None) last_worn date so the gap math
        # below is None-safe (the filter guarantees last_worn is set).
        candidates = [
            (i, i.last_worn)
            for i in items
            if (i.wear_count or 0) > 0 and i.last_worn and i.last_worn <= forgotten_cutoff
        ]
        forgotten_gem: DigestItem | None = None
        if candidates:
            # Most-neglected first: longest gap, then highest price as tiebreak.
            gem, last_worn = max(candidates, key=lambda c: ((today - c[1]).days, float(c[0].price or 0)))
            forgotten_gem = DigestItem(
                item_id=str(gem.id),
                name=gem.name,
                category=gem.category,
                detail=f"{(today - last_worn).days} days ago",
            )

        # ── Utilization (share of the closet worn at least once) ──────────────
        total = len(items)
        worn_ever = sum(1 for i in items if (i.wear_count or 0) > 0)
        utilization_rate = round(worn_ever / total * 100, 1) if total else 0.0

        headline = self._digest_headline(
            wears_logged=wears_logged,
            items_worn=items_worn,
            most_worn=most_worn,
            new_items=new_items,
            forgotten_gem=forgotten_gem,
        )

        return WeeklyDigest(
            week_start=window_start.isoformat(),
            week_end=today.isoformat(),
            wears_logged=wears_logged,
            items_worn=items_worn,
            new_items=new_items,
            utilization_rate=utilization_rate,
            most_worn=most_worn,
            best_value=best_value,
            forgotten_gem=forgotten_gem,
            headline=headline,
        )

    @staticmethod
    def _digest_headline(
        *,
        wears_logged: int,
        items_worn: int,
        most_worn: DigestItem | None,
        new_items: int,
        forgotten_gem: DigestItem | None,
    ) -> str:
        """A single warm, deterministic summary sentence for the recap."""
        if wears_logged == 0:
            if new_items > 0:
                return f"You added {new_items} new piece{'s' if new_items != 1 else ''} this week — log a wear to see your style come to life."
            return "Quiet week — log what you wear to unlock your weekly style story."
        pieces = f"{wears_logged} wear{'s' if wears_logged != 1 else ''} across {items_worn} piece{'s' if items_worn != 1 else ''}"
        if most_worn:
            return f"{pieces} this week — {most_worn.name} led the rotation."
        if forgotten_gem:
            return f"{pieces} this week. {forgotten_gem.name} is overdue for a comeback."
        return f"{pieces} this week. Nice rhythm — keep it going."
