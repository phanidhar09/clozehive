"""
Gemini Vision Service — clothing detection + metadata via Gemini 1.5 Flash.

One API call returns ALL detected items with bounding boxes AND full fashion
metadata.  Gemini 1.5 Flash is ~3–5× faster than GPT-4o for this task.

Fallback: if GEMINI_API_KEY is not set the caller should use the existing
OpenAI-based fashion_analysis_service instead.

Return shape (same contract as fashion_analysis_service.analyze_fashion_image):
  {
    "total_items_detected": int,
    "items": [
      {
        "item_id":         str,      # "item_001", "item_002", …
        "category":        str,      # top/bottom/footwear/outerwear/accessory/dress/other
        "subcategory":     str|null,
        "name":            str,
        "description":     str|null,
        "gender":          str,      # male/female/unisex
        "fit":             str|null,
        "sleeve_type":     str|null,
        "primary_color":   str|null,
        "secondary_color": str|null,
        "pattern":         str|null,
        "material":        str|null,
        "brand":           str|null,
        "occasions":       list[str],
        "season":          list[str],
        "style_tags":      list[str],
        "bbox":            {"x_min", "y_min", "x_max", "y_max"},  # fractions 0–1
        "detection_confidence": float,
        "segmentation_quality": str,   # high/medium/low
      }
    ]
  }
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langsmith import traceable

from app.api.v1.wardrobe.services.fashion_detection_prompt import (
    FASHION_DETECTION_PROMPT,
    FashionDetection,
    to_detection_dict,
)
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("gemini_service")

# Transient-error retry: Gemini occasionally returns 429/503 or an empty body
# under load. One quick retry recovers most of these before we fall back to OpenAI.
_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_S = 0.6

# ── Lazy client singleton (google-genai SDK) ──────────────────────────────────

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("gemini_client_initialized", model=settings.gemini_model)
    return _client


# The detection prompt + structured-output schema live in fashion_detection_prompt
# so the Gemini and OpenAI paths can never drift apart.


# ── JSON cleaning ─────────────────────────────────────────────────────────────


def _clean_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


# ── Public API ────────────────────────────────────────────────────────────────


def is_available() -> bool:
    """True only when GEMINI_API_KEY looks like a real developer key (.env placeholders skipped)."""
    k = settings.gemini_api_key.strip()
    if len(k) < 24:
        return False
    low = k.lower().replace("-", "").replace("_", "")
    # Copy-paste artefacts from `.env.example`
    if "yourgeminiapikey" in low or "yourgeminikey" in low:
        return False
    if "placeholder" in low or low.startswith("replace"):
        return False
    return True


@traceable(name="gemini_detect_and_classify", run_type="llm")
async def detect_and_classify(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """
    Send image to Gemini for combined detection + metadata.

    Uses a strict ``response_schema`` (``FashionDetection``) so the model returns
    structurally-guaranteed JSON — no free-form parsing of bbox keys or coercion of
    list fields needed. Retries once on transient API errors before giving up; the
    caller (vision_pipeline_service) then falls back to OpenAI.

    Returns the standard detection dict (same shape as fashion_analysis_service).
    Raises on persistent API error or validation failure — callers should catch and fall back.
    """
    from google.genai import types

    client = _get_client()

    # Gemini accepts inline image bytes
    effective_mime = (
        media_type if media_type in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
    )

    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=4096,
        response_mime_type="application/json",
        # Structured output — Gemini conforms its JSON to this schema, eliminating
        # malformed bbox / missing-field classes of failure at the source.
        response_schema=FashionDetection,
    )

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=effective_mime),
                    FASHION_DETECTION_PROMPT,
                ],
                config=config,
            )
            return _parse_response(response)
        except (ValueError, json.JSONDecodeError):
            # Bad/empty model output — re-prompting rarely helps; fail fast to fallback.
            raise
        except Exception as exc:  # transient API errors (429/503/timeouts)
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                logger.warning("gemini_api_retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(_RETRY_BACKOFF_S * attempt)
                continue
            logger.error("gemini_api_error", error=str(exc))
            raise

    # Unreachable, but keeps type-checkers satisfied.
    raise last_exc if last_exc else RuntimeError("gemini detection failed")


def _parse_response(response: Any) -> dict[str, Any]:
    """Validate a Gemini response into the standard detection dict.

    Prefers the SDK's already-validated ``.parsed`` instance; falls back to parsing
    ``.text`` through the same Pydantic schema so a single code path handles both.
    """
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, FashionDetection):
        result = to_detection_dict(parsed)
        logger.info("gemini_detection_complete", items=result["total_items_detected"])
        return result

    raw_text = (getattr(response, "text", None) or "").strip()
    if not raw_text:
        raise ValueError("Gemini returned an empty response")
    try:
        validated = FashionDetection.model_validate_json(_clean_json(raw_text))
    except Exception as exc:
        logger.error("gemini_json_parse_error", error=str(exc), preview=raw_text[:400])
        raise ValueError(f"Gemini returned invalid JSON: {exc}") from exc

    result = to_detection_dict(validated)
    logger.info("gemini_detection_complete", items=result["total_items_detected"])
    return result
