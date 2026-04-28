"""
Vision AI service — analyses clothing images using GPT-4o Vision.
Falls back to a structured mock response if OpenAI is unavailable.

Two modes:
  analyse_image()        — single clothing item analysis + bg removal
  analyse_outfit_image() — full-body photo: detects all worn items + bg removal
"""
import base64
import json
import re

from openai import OpenAI

from app.core.config import settings
from app.models.schemas import (
    DetectedOutfitItem,
    OutfitAnalysisResponse,
    VisionAnalysisResponse,
)
from app.services.bg_removal_service import remove_background

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    return json.loads(text)


# ─── Single item analysis ──────────────────────────────────────────────────────

VISION_PROMPT = """
You are a professional fashion analyst. Analyse the clothing item in the image and respond ONLY with a valid JSON object matching this exact schema:

{
  "garment_type": "<shirt|pants|dress|jacket|skirt|shoes|accessory|etc>",
  "fabric": "<cotton|silk|polyester|wool|denim|linen|synthetic|blend|unknown>",
  "color_primary": "<main color name>",
  "color_secondary": "<secondary color or empty string>",
  "pattern": "<solid|striped|floral|checked|printed|geometric|plain>",
  "season": "<spring|summer|autumn|winter|all-season>",
  "occasion": ["<casual|formal|party|work|sport|beach|etc>"],
  "care_instructions": ["<wash cold|hand wash|dry clean|tumble dry low|etc>"],
  "wearing_tips": ["<one tip>", "<another tip>"],
  "eco_score": <integer 1-10 based on fabric sustainability>,
  "confidence": <float 0-1>,
  "raw_description": "<one sentence describing the garment>"
}

Rules:
- eco_score: natural fabrics (cotton, linen, wool) = 7-9, synthetic = 2-4, blend = 5-6
- confidence: 0.9 if clearly visible, 0.7 if partially visible, 0.5 if unclear
- Return ONLY the JSON, no markdown fences, no extra text.
"""


def analyse_image(image_bytes: bytes, media_type: str = "image/jpeg") -> VisionAnalysisResponse:
    """Analyse a single clothing item image. Removes background automatically."""
    # Remove background first
    processed_b64, processed_media_type = remove_background(image_bytes)

    if not settings.openai_api_key:
        result = _mock_response()
        result.processed_image_base64 = processed_b64
        result.processed_image_media_type = processed_media_type
        return result

    try:
        client = _get_client()
        b64 = _encode_image(image_bytes)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "high"}},
                    ],
                }
            ],
            max_tokens=600,
            temperature=0.2,
        )
        raw = response.choices[0].message.content
        data = _extract_json(raw)
        result = VisionAnalysisResponse(**data)
        result.processed_image_base64 = processed_b64
        result.processed_image_media_type = processed_media_type
        return result
    except Exception as e:
        print(f"[VisionService] Error: {e}")
        result = _mock_response()
        result.processed_image_base64 = processed_b64
        result.processed_image_media_type = processed_media_type
        return result


def _mock_response() -> VisionAnalysisResponse:
    return VisionAnalysisResponse(
        garment_type="shirt",
        fabric="cotton",
        color_primary="white",
        color_secondary="",
        pattern="solid",
        season="all-season",
        occasion=["casual", "work"],
        care_instructions=["Machine wash cold", "Tumble dry low", "Do not bleach"],
        wearing_tips=["Pair with chinos for smart casual", "Tuck in for a formal look"],
        eco_score=8,
        confidence=0.5,
        raw_description="A plain white cotton shirt suitable for everyday wear",
    )


# ─── Outfit / full-body analysis ──────────────────────────────────────────────

OUTFIT_DETECTION_PROMPT = """
You are a professional fashion analyst. The image shows a person wearing a complete outfit.
Identify EVERY distinct clothing item and accessory the person is wearing.

Respond ONLY with a valid JSON object:

{
  "is_outfit_photo": true,
  "items": [
    {
      "garment_type": "<shirt|t-shirt|pants|jeans|dress|jacket|coat|skirt|shorts|shoes|sneakers|boots|bag|belt|hat|scarf|etc>",
      "suggested_name": "<concise display name, e.g. 'White Oxford Shirt'>",
      "category": "<tops|bottoms|shoes|outerwear|dresses|accessories>",
      "fabric": "<cotton|silk|polyester|wool|denim|linen|synthetic|blend|unknown>",
      "color_primary": "<main color>",
      "color_secondary": "<secondary color or empty string>",
      "pattern": "<solid|striped|floral|checked|printed|geometric|plain>",
      "season": "<spring|summer|autumn|winter|all-season>",
      "occasion": ["<casual|formal|party|work|sport|beach|etc>"],
      "eco_score": <integer 1-10>,
      "description": "<one sentence about this specific item>"
    }
  ]
}

Rules:
- List every visible garment separately (shirt, pants, shoes, belt, bag, etc.)
- eco_score: natural fabrics 7-9, synthetic 2-4, blend 5-6
- category must be one of: tops, bottoms, shoes, outerwear, dresses, accessories
- Return ONLY the JSON, no markdown, no extra text.
"""


def analyse_outfit_image(image_bytes: bytes, media_type: str = "image/jpeg") -> OutfitAnalysisResponse:
    """
    Detect all clothing items worn in a full-body photo.
    Also removes the background from the image.
    """
    processed_b64, processed_media_type = remove_background(image_bytes)

    if not settings.openai_api_key:
        result = _mock_outfit_response()
        result.processed_image_base64 = processed_b64
        result.processed_image_media_type = processed_media_type
        return result

    try:
        client = _get_client()
        b64 = _encode_image(image_bytes)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OUTFIT_DETECTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "high"}},
                    ],
                }
            ],
            max_tokens=1200,
            temperature=0.2,
        )
        raw = response.choices[0].message.content
        data = _extract_json(raw)

        items = [DetectedOutfitItem(**item) for item in data.get("items", [])]
        result = OutfitAnalysisResponse(
            is_outfit_photo=True,
            items=items,
            processed_image_base64=processed_b64,
            processed_image_media_type=processed_media_type,
        )
        return result
    except Exception as e:
        print(f"[VisionService] Outfit analysis error: {e}")
        result = _mock_outfit_response()
        result.processed_image_base64 = processed_b64
        result.processed_image_media_type = processed_media_type
        return result


def _mock_outfit_response() -> OutfitAnalysisResponse:
    return OutfitAnalysisResponse(
        is_outfit_photo=True,
        items=[
            DetectedOutfitItem(
                garment_type="shirt",
                suggested_name="White Oxford Shirt",
                category="tops",
                fabric="cotton",
                color_primary="white",
                color_secondary="",
                pattern="solid",
                season="all-season",
                occasion=["casual", "work"],
                eco_score=8,
                description="A classic white Oxford button-up shirt",
            ),
            DetectedOutfitItem(
                garment_type="jeans",
                suggested_name="Blue Slim Jeans",
                category="bottoms",
                fabric="denim",
                color_primary="blue",
                color_secondary="",
                pattern="solid",
                season="all-season",
                occasion=["casual"],
                eco_score=5,
                description="Blue slim-fit denim jeans",
            ),
            DetectedOutfitItem(
                garment_type="sneakers",
                suggested_name="White Sneakers",
                category="shoes",
                fabric="synthetic",
                color_primary="white",
                color_secondary="",
                pattern="solid",
                season="all-season",
                occasion=["casual", "sport"],
                eco_score=3,
                description="White casual sneakers",
            ),
        ],
    )
