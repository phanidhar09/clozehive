"""
Vision service — GPT-4o Vision garment analysis.
Accepts base64-encoded image bytes and returns structured clothing attributes.
"""

from __future__ import annotations

import base64
import json

from openai import AsyncOpenAI

from shared.config import get_settings
from shared.logger import get_logger
from shared.schemas import VisionAnalysisResult

logger = get_logger(__name__)

_PROMPT = """
You are a fashion AI expert. Analyse this clothing item image and return ONLY valid JSON
(no markdown, no code fences) with this exact schema:

{
  "garment_type": "<shirt|pants|dress|jacket|shoes|bag|accessory|other>",
  "fabric": "<cotton|polyester|wool|silk|denim|leather|linen|blend|synthetic|unknown>",
  "color_primary": "<primary colour>",
  "color_secondary": "<secondary colour or empty string>",
  "pattern": "<solid|stripes|plaid|floral|geometric|animal print|abstract|other|none>",
  "season": "<spring|summer|fall|winter|all-season>",
  "occasion": ["<casual|formal|business|athletic|evening|beach|outdoor>"],
  "care_instructions": ["<instruction>"],
  "wearing_tips": ["<tip>"],
  "eco_score": <integer 1-10>,
  "confidence": <float 0.0-1.0>,
  "raw_description": "<one-sentence plain-English description>"
}

Return only the JSON object — no other text.
""".strip()


async def analyse_image(image_base64: str, media_type: str = "image/jpeg") -> VisionAnalysisResult:
    """
    Call GPT-4o Vision to analyse a garment image.

    Args:
        image_base64: Base64-encoded image bytes (no data-URL prefix).
        media_type:   MIME type, e.g. 'image/jpeg', 'image/png', 'image/webp'.

    Returns:
        VisionAnalysisResult with structured garment attributes.
    """
    settings = get_settings()
    logger.info("Analysing garment image (media_type=%s, bytes≈%d)", media_type, len(image_base64) * 3 // 4)

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=800,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )

        raw = response.choices[0].message.content or "{}"
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)

        result = VisionAnalysisResult(**data)
        logger.info("Vision analysis complete: %s / %s", result.garment_type, result.color_primary)
        return result

    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error from GPT-4o vision: %s", exc)
        return _mock_result()
    except Exception as exc:
        logger.error("Vision API error: %s", exc, exc_info=True)
        return _mock_result()


def _mock_result() -> VisionAnalysisResult:
    """Fallback when the API is unavailable or returns malformed data."""
    logger.warning("Returning mock vision result")
    return VisionAnalysisResult(
        garment_type="shirt",
        fabric="cotton",
        color_primary="white",
        color_secondary="",
        pattern="solid",
        season="all-season",
        occasion=["casual"],
        care_instructions=["Machine wash cold", "Tumble dry low"],
        wearing_tips=["Pair with jeans for a casual look"],
        eco_score=6,
        confidence=0.0,
        raw_description="Mock result — API unavailable.",
    )
