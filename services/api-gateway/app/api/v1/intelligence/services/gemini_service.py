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
import time
from typing import Any

from langsmith import traceable

from app.api.v1.wardrobe.services.fashion_detection_prompt import (
    FASHION_DETECTION_PROMPT,
    FashionDetection,
    to_detection_dict,
)
from app.core.analytics import LLMTelemetry, capture_llm_generation
from app.core.config import get_settings
from app.core.llm_pricing import cost_usd
from app.core.logging import get_logger
from app.core.metrics import record_ai_cost, record_ai_tokens

settings = get_settings()
logger = get_logger("gemini_service")

# Transient-error retry: Gemini occasionally returns 503 or an empty body under
# load. One quick retry recovers most of these before we fall back to OpenAI.
_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_S = 0.6


def _is_quota_error(exc: Exception) -> bool:
    """True for 429 / RESOURCE_EXHAUSTED quota errors.

    These are not transient: the free-tier per-minute/day quota won't reset
    inside our sub-second backoff (the API's own ``retryDelay`` is ~17s), so a
    local retry just burns latency on every upload before we fall back to
    OpenAI. Detect them so we can fail fast to the fallback instead.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    # Fall back to the structured status name only — matching a bare "429"
    # substring risks false-positives on trace ids, byte counts, or timestamps
    # that happen to contain those digits.
    return "RESOURCE_EXHAUSTED" in str(exc).upper()


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
def _capture_generation(response: Any, elapsed: float, *, is_error: bool = False) -> None:
    """Token/cost capture for Gemini vision — same $ai_generation schema as the
    OpenAI paths, with provider="gemini". Uses the SDK's ``usage_metadata``
    (prompt_token_count / candidates_token_count); a rough image-proxy estimate
    when absent, so dashboards never show a silent zero. Never raises.
    """
    try:
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            prompt_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
            completion_tokens = int(getattr(meta, "candidates_token_count", 0) or 0)
            token_source = "api"
        else:
            prompt_tokens, completion_tokens, token_source = 1000, 0, "estimated"
        input_cost, output_cost, _ = cost_usd(settings.gemini_model, prompt_tokens, completion_tokens)
        record_ai_tokens(settings.gemini_model, prompt=prompt_tokens, completion=completion_tokens)
        record_ai_cost(settings.gemini_model, input_cost + output_cost)
        capture_llm_generation(
            model=settings.gemini_model,
            provider="gemini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            latency_seconds=elapsed,
            token_source=token_source,
            telemetry=LLMTelemetry(operation="vision_detection"),
            is_error=is_error,
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break detection
        logger.debug("gemini_generation_capture_failed", error=str(exc))


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
        started = time.perf_counter()
        try:
            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=effective_mime),
                    FASHION_DETECTION_PROMPT,
                ],
                config=config,
            )
            _capture_generation(response, time.perf_counter() - started)
            return _parse_response(response)
        except (ValueError, json.JSONDecodeError):
            # Bad/empty model output — re-prompting rarely helps; fail fast to fallback.
            raise
        except Exception as exc:  # transient API errors (503/timeouts) + quota 429s
            last_exc = exc
            # Quota exhaustion won't clear inside our sub-second backoff — don't
            # waste a retry, fail straight to the OpenAI fallback. Logged at
            # warning (not error) because the caller recovers gracefully.
            if _is_quota_error(exc):
                logger.warning("gemini_quota_exhausted", model=settings.gemini_model, error=str(exc))
                raise
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
