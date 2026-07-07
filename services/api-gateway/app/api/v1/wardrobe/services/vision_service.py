"""Consolidated vision service for garment image analysis (OpenAI vision)."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from langsmith import traceable
from openai import AsyncOpenAI

from app.api.v1.wardrobe.schemas.vision_canonical import (
    normalized_to_bulk_api_dict,
    normalized_to_legacy_upload_dict,
    parse_vision_ai_payload,
)
from app.core.analytics import LLMTelemetry
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.openai_tracing import make_openai_client, wrap_openai_client

settings = get_settings()
logger = get_logger("vision_service")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = wrap_openai_client(make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url))
    return _client


def _capture_vision_generation(
    *,
    model: str,
    messages: list[dict[str, Any]],
    output_text: str,
    usage: Any,
    elapsed: float,
    operation: str,
    telemetry: LLMTelemetry | None,
    is_error: bool = False,
) -> None:
    """Token/cost capture for vision calls — same $ai_generation plumbing as chat.

    Lazy import: ai_service lives in the intelligence package, which imports
    wardrobe modules at package level; importing it at module scope here would
    create a cycle.
    """
    try:
        from app.api.v1.intelligence.services.ai_service import _record_generation

        _record_generation(
            model=model,
            messages=messages,
            output_chars=len(output_text),
            usage=usage,
            elapsed=elapsed,
            telemetry=telemetry or LLMTelemetry(operation=operation),
            is_error=is_error,
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break vision
        logger.debug("vision_generation_capture_failed", error=str(exc))


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
        if "```" in text:
            text = text[: text.index("```")]
    return text.strip()


def _fallback_raw(reason: str) -> dict[str, Any]:
    logger.warning("vision_fallback", reason=reason)
    return {
        "name": "Unknown Clothing Item",
        "category": "tops",
        "color": "Unknown",
        "brand": "",
        "material": "",
        "pattern": "",
        "occasion": ["casual"],
        "tags": [],
        "confidence": 0.0,
        "notes": f"Auto-analysis unavailable ({reason}). Please fill in details manually.",
    }


def _bulk_fallback_raw(reason: str) -> dict[str, Any]:
    logger.warning("bulk_vision_fallback", reason=reason)
    return {
        "name": "Clothing Item",
        "category": "tops",
        "subcategory": "Unknown",
        "description": "AI analysis unavailable. Please fill in details manually.",
        "primary_color": "Unknown",
        "secondary_colors": [],
        "pattern": "Unknown",
        "material": "Unknown",
        "occasion_tags": ["Casual"],
        "season_tags": [],
        "style_tags": [],
        "fit": "Regular",
        "brand": "",
        "confidence_score": 0.0,
        "warnings": [f"Auto-analysis unavailable: {reason}"],
    }


# ── Standard single-item analysis (used by /upload, /bulk-upload) ─────────────


@traceable(name="gateway_vision_analyze_image", run_type="chain")
async def analyze_image(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
    *,
    telemetry: LLMTelemetry | None = None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        return normalized_to_legacy_upload_dict(
            parse_vision_ai_payload(
                _fallback_raw("No OpenAI credentials — add OPENAI_API_KEY to your `.env` and restart the API server"),
                source="fallback",
            )
        )

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{image_b64}"
    prompt = (
        "Analyse this clothing item and return ONLY valid JSON with fields: "
        "name, category (tops, bottoms, shoes, outerwear, dresses, accessories, other), "
        "color (specific shade e.g. navy blue, charcoal, ivory — not just 'blue'), "
        "brand (null unless logo is clearly visible), material (read the visible texture — "
        "denim/cotton/silk/wool/polyester/leather/unknown), pattern, occasion array, tags array, "
        "confidence (0.0-1.0 float — set low when image quality is poor or item is partially visible), "
        "notes (any caveats about detection quality)."
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    started = time.perf_counter()
    try:
        response = await _get_client().chat.completions.create(  # type: ignore[call-overload]
            # Categorization tier: name/category/color for a single clean item
            # photo — the mini vision model handles this reliably at ~15x lower
            # cost. Rich extraction (fit, material texture) lives in
            # analyze_for_bulk on the flagship model.
            model=settings.vision_analysis_model,
            max_tokens=800,
            timeout=30.0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        msg = response.choices[0].message
        text = (msg.content or "").strip()
        _capture_vision_generation(
            model=settings.vision_analysis_model,
            messages=messages,
            output_text=text,
            usage=getattr(response, "usage", None),
            elapsed=time.perf_counter() - started,
            operation="vision_categorize",
            telemetry=telemetry,
        )
        raw = json.loads(_clean_json(text))
        if not isinstance(raw, dict):
            raise ValueError("Vision response is not a JSON object")
        n = parse_vision_ai_payload(raw, source="openai")
        if n.confidence < 0.40:
            logger.warning(
                "vision_low_confidence",
                confidence=n.confidence,
                name=n.name,
                category=n.category,
            )
        return normalized_to_legacy_upload_dict(n)
    except BaseException as exc:
        logger.error("vision_analysis_failed", error=str(exc))
        _capture_vision_generation(
            model=settings.vision_analysis_model,
            messages=messages,
            output_text="",
            usage=None,
            elapsed=time.perf_counter() - started,
            operation="vision_categorize",
            telemetry=telemetry,
            is_error=True,
        )
        return normalized_to_legacy_upload_dict(parse_vision_ai_payload(_fallback_raw(str(exc)), source="fallback"))


# ── Rich bulk-ingestion analysis (used by smart-ingest, closet preview fallback) ─

_BULK_PROMPT = """\
You are an expert fashion AI. Analyse this single clothing item image and return \
ONLY valid JSON with the fields below. Be precise — do not hallucinate details.

COLOR — use specific shade names (navy blue, charcoal, ivory, burgundy, sage green, \
rust, camel, cobalt, etc.). Never use bare "blue", "green", or "gray".

MATERIAL — read the visible texture and drape:
  diagonal twill, rigid body → denim | matte flat weave → cotton or linen
  liquid-draped folds → silk or satin | fuzzy warm surface → wool or fleece
  fine ribbing → knit | high-sheen smooth → polyester or synthetic
  stiff grained surface → leather or faux-leather
Output "unknown" if texture is indeterminate — never guess.

{
  "name": "Specific item name e.g. Charcoal Slim-Fit Chinos or Ivory Cable-Knit Sweater",
  "category": "tops | bottoms | shoes | outerwear | dresses | accessories | other",
  "subcategory": "e.g. T-Shirt | Slim Jeans | Sneakers | Blazer | Maxi Dress | Belt",
  "description": "One concrete sentence about the item's visible qualities — color, cut, texture",
  "primary_color": "Specific shade e.g. navy blue | charcoal | ivory | burgundy",
  "secondary_colors": ["list of any accent colors, empty if none"],
  "pattern": "Solid | Striped | Plaid | Checked | Floral | Graphic | Animal Print | Tie-Dye | Camo | Houndstooth | Paisley | Other",
  "material": "Cotton | Denim | Leather | Faux-leather | Polyester | Silk | Wool | Linen | Fleece | Knit | Synthetic | Unknown",
  "occasion_tags": ["Casual", "Business Casual", "Formal", "Sport", "Beach", "Date Night", "Travel"],
  "season_tags": ["Spring", "Summer", "Fall", "Winter", "All-Season"],
  "style_tags": ["Minimal", "Streetwear", "Classic", "Bohemian", "Preppy", "Sporty", "Elegant", "Vintage", "Athleisure", "Workwear"],
  "fit": "Slim | Regular | Relaxed | Oversized | Tailored",
  "brand": "Brand name if logo is clearly and fully legible, else empty string",
  "confidence_score": 0.0-1.0 float reflecting detection certainty
}

Return ONLY valid JSON. No markdown fences, no prose, no trailing commas."""


@traceable(name="gateway_vision_analyze_for_bulk", run_type="chain")
async def analyze_for_bulk(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
    *,
    extra_instruction: str | None = None,
    telemetry: LLMTelemetry | None = None,
) -> dict[str, Any]:
    """
    Rich garment analysis for ingest and preview fallback.

    ``extra_instruction`` is prepended to the prompt for non-standard inputs —
    e.g. a product-page screenshot, where the model must pick the single main
    garment out of site chrome and other products rather than assume one clean
    studio photo.

    Returns a dict with primary_color, occasion_tags, etc., merged with validated canonical fields.
    """
    if not settings.openai_api_key:
        raw_fb = _bulk_fallback_raw(
            "No OpenAI credentials — add OPENAI_API_KEY to your `.env` and restart the API server"
        )
        n = parse_vision_ai_payload(raw_fb, source="fallback")
        return normalized_to_bulk_api_dict(n, raw=raw_fb)

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{image_b64}"
    prompt_text = f"{extra_instruction}\n\n{_BULK_PROMPT}" if extra_instruction else _BULK_PROMPT
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]
    started = time.perf_counter()
    try:
        response = await _get_client().chat.completions.create(  # type: ignore[call-overload]
            # Enrichment tier — deliberately the flagship model + detail:high.
            # This pass reads fabric texture, fit, and pattern (and picks the
            # main garment out of product-page screenshots) — the tasks most
            # sensitive to model quality. Do not downgrade in a cost pass
            # without a vision golden set to measure the regression — tier the
            # detection/categorization calls instead (see config
            # vision_detection_model / vision_analysis_model).
            model=settings.openai_model,
            max_tokens=1500,
            timeout=45.0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        msg = response.choices[0].message
        text = (msg.content or "").strip()
        _capture_vision_generation(
            model=settings.openai_model,
            messages=messages,
            output_text=text,
            usage=getattr(response, "usage", None),
            elapsed=time.perf_counter() - started,
            operation="vision_enrich",
            telemetry=telemetry,
        )
        data = json.loads(_clean_json(text))
        if not isinstance(data, dict):
            raise ValueError("Response is not a JSON object")
        n = parse_vision_ai_payload(data, source="bulk")

        # Warn on low-confidence detections — caller should prompt user to verify
        if n.confidence < 0.50:
            logger.warning(
                "bulk_vision_low_confidence",
                confidence=n.confidence,
                name=n.name,
                category=n.category,
            )
            if not data.get("warnings"):
                data["warnings"] = []
            data["warnings"].append(
                f"Low detection confidence ({n.confidence:.0%}). Please review and correct details before saving."
            )

        return normalized_to_bulk_api_dict(n, raw=data)
    except BaseException as exc:
        logger.error("bulk_vision_analysis_failed", error=str(exc))
        _capture_vision_generation(
            model=settings.openai_model,
            messages=messages,
            output_text="",
            usage=None,
            elapsed=time.perf_counter() - started,
            operation="vision_enrich",
            telemetry=telemetry,
            is_error=True,
        )
        raw_fb = _bulk_fallback_raw(str(exc))
        n = parse_vision_ai_payload(raw_fb, source="fallback")
        return normalized_to_bulk_api_dict(n, raw=raw_fb)
