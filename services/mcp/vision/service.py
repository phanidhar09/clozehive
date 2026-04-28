"""Vision service — GPT-4o image analysis for closet items."""

from __future__ import annotations

import base64
import json
import os

import httpx

from shared.schemas import VisionAnalysisResult
from shared.logger import get_logger

logger = get_logger("vision.service")

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

_SYSTEM = """\
You are a professional fashion analyst. Analyse the clothing item in the image
and return ONLY valid JSON (no markdown fences) with the following fields:
  name        – short descriptive name (e.g. "Navy Blue Slim-Fit Chinos")
  category    – one of: tops, bottoms, shoes, outerwear, dresses, accessories
  color       – primary color name
  brand       – brand name if visible, else ""
  material    – fabric/material if identifiable, else ""
  pattern     – pattern if visible (solid, striped, floral, plaid, …), else ""
  occasion    – array of applicable occasions (casual, formal, sport, beach, …)
  tags        – descriptive tags array (lightweight, breathable, vintage, …)
  eco_score   – float 0–10 if material allows estimation, else null
  confidence  – float 0–1 reflecting your certainty
  notes       – brief styling note
"""


def _build_data_url(image_base64: str, media_type: str) -> str:
    if image_base64.startswith("data:"):
        return image_base64
    return f"data:{media_type};base64,{image_base64}"


def _mock_result(reason: str = "") -> VisionAnalysisResult:
    """Fallback when OpenAI is unavailable."""
    logger.warning("vision_mock_fallback", reason=reason)
    return VisionAnalysisResult(
        name="Unknown Clothing Item",
        category="tops",
        color="Unknown",
        confidence=0.0,
        notes=f"Auto-analysis unavailable ({reason}). Please fill in details manually.",
    )


async def analyse_image(image_base64: str, media_type: str = "image/jpeg") -> VisionAnalysisResult:
    """
    Send the image to GPT-4o Vision and parse the structured response.

    Args:
        image_base64: Base64-encoded image data (with or without data-URL prefix).
        media_type:   MIME type, e.g. "image/jpeg" or "image/png".

    Returns:
        VisionAnalysisResult with detected clothing attributes.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return _mock_result("OPENAI_API_KEY not set")

    data_url = _build_data_url(image_base64, media_type)

    payload = {
        "model": _MODEL,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                    {"type": "text", "text": "Analyse this clothing item."},
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _OPENAI_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        return VisionAnalysisResult(**parsed)

    except httpx.HTTPStatusError as exc:
        logger.error("vision_api_error", status=exc.response.status_code)
        return _mock_result(f"API error {exc.response.status_code}")
    except json.JSONDecodeError as exc:
        logger.error("vision_parse_error", error=str(exc))
        return _mock_result("JSON parse error")
    except Exception as exc:
        logger.error("vision_unexpected_error", error=str(exc))
        return _mock_result(str(exc))


def encode_file(file_bytes: bytes, media_type: str) -> str:
    """Convenience: encode raw bytes to base64 string."""
    return base64.b64encode(file_bytes).decode("utf-8")
