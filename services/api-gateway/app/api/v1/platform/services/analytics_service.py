"""AnalyticsService for closet insights."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services.purchase_gap_service import detect_and_save_gaps
from app.api.v1.platform.schemas.analytics import (
    CategoryCoverageItem,
    CategoryStats,
    ClosetAnalyticsResponse,
    ClosetSummary,
    ColorStats,
    OutfitReadiness,
    PurchaseGapInsight,
)
from app.models.closet import ClosetItem


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
