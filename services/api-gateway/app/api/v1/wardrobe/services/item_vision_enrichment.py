"""Merge full-scene detection with per-crop OpenAI analysis (bulk vision schema)."""

from __future__ import annotations

from typing import Any

from app.api.v1.wardrobe.services import vision_service
from app.core.logging import get_logger

logger = get_logger("item_vision_enrichment")


def _bulk_is_fallback(bulk: dict[str, Any]) -> bool:
    w = bulk.get("warnings")
    if isinstance(w, list) and w:
        return any("unavailable" in str(x).lower() or "not configured" in str(x).lower() for x in w)
    desc = str(bulk.get("description") or "")
    if "unavailable" in desc.lower() and not bulk.get("primary_color"):
        return True
    return False


def _first_secondary(bulk: dict[str, Any]) -> str | None:
    sec = bulk.get("secondary_colors")
    if isinstance(sec, list) and sec:
        return str(sec[0]) if sec[0] else None
    return None


async def enrich_detection_with_crop_analysis(
    rgba_png_bytes: bytes,
    detection: dict[str, Any],
) -> dict[str, Any]:
    """
    Run OpenAI vision on a single cropped / background-removed item and merge
    into detection fields. Prefers crop-level detail when confident.
    """
    out = dict(detection)
    try:
        bulk = await vision_service.analyze_for_bulk(rgba_png_bytes, "image/png")
    except Exception as exc:
        logger.warning("crop_enrich_failed", error=str(exc))
        return out

    if not isinstance(bulk, dict) or _bulk_is_fallback(bulk):
        return out

    if bulk.get("name") and str(bulk["name"]).strip().lower() not in ("unknown",):
        out["name"] = str(bulk["name"]).strip()
    if bulk.get("description"):
        out["description"] = str(bulk["description"]).strip()

    if bulk.get("category"):
        out["category"] = str(bulk["category"]).strip().lower()
    if bulk.get("subcategory"):
        out["subcategory"] = str(bulk["subcategory"]).strip()

    if bulk.get("primary_color"):
        out["primary_color"] = str(bulk["primary_color"]).strip()
    sc = _first_secondary(bulk)
    if sc:
        out["secondary_color"] = sc
    if bulk.get("pattern"):
        out["pattern"] = str(bulk["pattern"]).strip()
    if bulk.get("material"):
        out["material"] = str(bulk["material"]).strip()
    if bulk.get("fit"):
        out["fit"] = str(bulk["fit"]).strip()
    if bulk.get("brand"):
        out["brand"] = str(bulk["brand"]).strip()

    if isinstance(bulk.get("occasion_tags"), list) and bulk["occasion_tags"]:
        out["occasions"] = [str(x) for x in bulk["occasion_tags"] if x]
    if isinstance(bulk.get("season_tags"), list) and bulk["season_tags"]:
        out["season"] = [str(x) for x in bulk["season_tags"] if x]
    if isinstance(bulk.get("style_tags"), list) and bulk["style_tags"]:
        out["style_tags"] = [str(x) for x in bulk["style_tags"] if x]

    conf = bulk.get("confidence_score")
    if isinstance(conf, (int, float)) and conf > 0:
        det_c = float(out.get("detection_confidence") or 0.0)
        out["detection_confidence"] = max(det_c, min(1.0, float(conf)))

    return out
