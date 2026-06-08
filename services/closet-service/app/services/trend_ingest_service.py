"""Fashion trend ingestion — pulls live trend signals into the RAG knowledge base.

Fetches rising fashion search queries per region from Google Trends (via the
``pytrends`` library), turns them into prompt-ready knowledge snippets, embeds
them, and upserts them into ``fashion_knowledge_documents`` with
``category="trend"``. The existing ``fashion_rag_service.get_fashion_context_for_prompt``
then surfaces them automatically at outfit/packing/chat inference time — no prompt
changes required.

Design notes:
  * ``pytrends`` scrapes an unofficial Google endpoint and rate-limits aggressively
    (HTTP 429). Every network call is wrapped so a failure for one region/term
    degrades gracefully (logged + skipped) rather than aborting the whole run.
  * The import is lazy/optional so the service (and its tests) load even when
    ``pytrends`` is not installed — callers get a clear "unavailable" result.
  * Trend docs are tagged ``source="google_trends"`` and refreshed by
    delete-then-insert per region, so the table never accumulates stale weeks.
  * To swap to a stable paid provider (e.g. SerpApi Google Trends), replace only
    ``_fetch_rising_queries`` — the embed/upsert path is provider-agnostic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.rag import FashionKnowledgeDocument
from app.services.embedding_service import generate_text_embedding
from app.services.location_intel_service import curated_region_names

logger = get_logger("trend_ingest_service")
settings = get_settings()

_SOURCE = "google_trends"
_CATEGORY = "trend"

# Seed terms expanded per region to surface rising fashion-adjacent queries.
_SEED_TERMS = ("outfit", "fashion", "what to wear", "style")

# Curated city → ISO-3166 country code for the Google Trends ``geo`` filter.
# Unmapped regions fall back to worldwide ("") so ingestion still succeeds.
_REGION_GEO: dict[str, str] = {
    "dubai": "AE", "abu dhabi": "AE", "doha": "QA", "cairo": "EG",
    "marrakech": "MA", "istanbul": "TR", "bangkok": "TH", "mumbai": "IN",
    "delhi": "IN", "hyderabad": "IN", "varanasi": "IN", "singapore": "SG",
    "bali": "ID", "miami": "US", "london": "GB", "paris": "FR",
    "amsterdam": "NL", "rome": "IT", "barcelona": "ES", "new york": "US",
    "los angeles": "US", "san francisco": "US", "chicago": "US",
    "tokyo": "JP", "kyoto": "JP", "sydney": "AU",
}

# How many rising queries to keep per region (keeps the snippet compact).
_MAX_QUERIES_PER_REGION = 12


def _iso_week_label(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _trend_title(region: str, week: str) -> str:
    return f"Trending fashion in {region.title()} ({week})"


def _build_snippet(region: str, queries: list[str], week: str) -> str:
    """Format rising fashion queries into a grounding paragraph for the LLM."""
    joined = ", ".join(queries)
    return (
        f"Rising fashion searches in {region.title()} during {week}: {joined}. "
        f"These reflect current local style interest and seasonal demand in {region.title()}. "
        "Use them as a signal for what feels fresh and locally relevant when recommending "
        "outfits or packing for this area — balance them against the user's own wardrobe, "
        "body profile, and the occasion rather than chasing trends blindly."
    )


def _fetch_rising_queries(region: str, geo: str) -> list[str]:
    """Return rising fashion-related search queries for a region via pytrends.

    Returns [] (never raises) on any pytrends/network failure so the caller can
    continue to the next region. Import is local so the module loads without the
    optional dependency installed.
    """
    try:
        from pytrends.request import TrendReq
    except ModuleNotFoundError:
        logger.warning("pytrends_not_installed")
        return []

    queries: list[str] = []
    seen: set[str] = set()
    try:
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        for term in _SEED_TERMS:
            try:
                pytrends.build_payload([term], timeframe="now 7-d", geo=geo)
                related = pytrends.related_queries() or {}
                bucket = related.get(term) or {}
                rising = bucket.get("rising")
                if rising is None or getattr(rising, "empty", True):
                    continue
                for q in rising["query"].tolist():
                    norm = str(q).strip().lower()
                    if norm and norm not in seen:
                        seen.add(norm)
                        queries.append(str(q).strip())
            except Exception as exc:
                # One flaky term shouldn't kill the region — log and continue.
                logger.warning("trend_term_failed", region=region, term=term, error=str(exc))
                continue
    except Exception as exc:
        logger.warning("trend_client_failed", region=region, error=str(exc))
        return []

    return queries[:_MAX_QUERIES_PER_REGION]


async def _upsert_region_trends(
    session: AsyncSession,
    region: str,
    queries: list[str],
    week: str,
) -> bool:
    """Replace this region's trend doc with a freshly-embedded one. Returns success."""
    content = _build_snippet(region, queries, week)
    embedding = await generate_text_embedding(f"Title: {_trend_title(region, week)}. {content}")

    # Delete any prior trend docs for this region+source so weeks don't accumulate.
    existing = await session.execute(
        select(FashionKnowledgeDocument).where(
            FashionKnowledgeDocument.category == _CATEGORY
        )
    )
    for doc in existing.scalars().all():
        tags = doc.tags or {}
        if tags.get("region") == region and tags.get("source") == _SOURCE:
            await session.delete(doc)

    session.add(
        FashionKnowledgeDocument(
            title=_trend_title(region, week),
            content=content,
            category=_CATEGORY,
            season=None,
            occasion=None,
            tags={
                "tags": queries,
                "region": region,
                "source": _SOURCE,
                "fetched_week": week,
            },
            embedding=embedding,
        )
    )
    return True


async def refresh_trends_for_regions(
    session: AsyncSession,
    regions: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch + embed + upsert fashion trends for the given regions.

    ``regions`` defaults to the curated destination set from
    ``location_intel_service`` so trends line up with the locations the app
    already personalizes for. Commits once at the end.
    """
    targets = [r.strip().lower() for r in (regions or curated_region_names()) if r.strip()]
    week = _iso_week_label()

    refreshed: list[str] = []
    skipped: list[str] = []

    for region in targets:
        geo = _REGION_GEO.get(region, "")
        queries = _fetch_rising_queries(region, geo)
        if not queries:
            skipped.append(region)
            continue
        try:
            await _upsert_region_trends(session, region, queries, week)
            refreshed.append(region)
        except Exception as exc:
            logger.warning("trend_upsert_failed", region=region, error=str(exc))
            skipped.append(region)

    await session.commit()
    logger.info(
        "trend_refresh_complete",
        week=week,
        refreshed=len(refreshed),
        skipped=len(skipped),
    )
    return {
        "week": week,
        "refreshed_count": len(refreshed),
        "refreshed": refreshed,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


# ── Weekly scheduler ──────────────────────────────────────────────────────────
# A lightweight asyncio loop (no extra dependency). A Redis lock keyed to the
# current ISO week ensures only ONE worker/instance runs the refresh per week,
# even with multiple uvicorn workers or replicas.

_LOCK_TTL_SECONDS = 6 * 60 * 60  # 6h — long enough to outlast a slow run


async def _acquire_weekly_lock(week: str) -> bool:
    """SET NX a per-week key so only one worker performs the refresh. Best-effort:
    if Redis is unavailable, returns True so a single-instance deploy still runs."""
    try:
        from app.services import cache_service

        redis = await cache_service.get_redis()
        key = cache_service.namespaced_key("trend_refresh_lock", week)
        # nx=True → only set if absent; ex=TTL → auto-expire so it self-heals.
        acquired = await redis.set(key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
        return bool(acquired)
    except Exception as exc:
        logger.warning("trend_lock_unavailable", error=str(exc))
        return True


async def _run_once_with_lock() -> None:
    """Run one refresh cycle if this worker wins the weekly lock."""
    week = _iso_week_label()
    if not await _acquire_weekly_lock(week):
        logger.info("trend_refresh_skipped_lock_held", week=week)
        return

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            result = await refresh_trends_for_regions(session)
            logger.info("trend_scheduled_refresh_ok", **{k: v for k, v in result.items() if k.endswith("_count") or k == "week"})
        except Exception as exc:
            await session.rollback()
            logger.warning("trend_scheduled_refresh_failed", error=str(exc))


async def trend_scheduler_loop() -> None:
    """Background loop: refresh trends every ``trend_refresh_interval_hours``.

    Cancelled cleanly on app shutdown. An initial short delay lets the app finish
    booting (DB/Redis up) before the first run.
    """
    interval = max(1, settings.trend_refresh_interval_hours) * 3600
    await asyncio.sleep(60)  # let startup settle
    while True:
        try:
            await _run_once_with_lock()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("trend_scheduler_iteration_failed", error=str(exc))
        await asyncio.sleep(interval)
