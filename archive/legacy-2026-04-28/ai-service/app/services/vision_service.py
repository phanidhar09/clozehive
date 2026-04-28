"""
Vision AI service — analyses clothing images using GPT-4o Vision.
Falls back to a structured mock response if OpenAI is unavailable.
"""
import base64
import json
import re
from pathlib import Path
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import VisionAnalysisResponse

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


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


def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    return json.loads(text)


def analyse_image(image_bytes: bytes, media_type: str = "image/jpeg") -> VisionAnalysisResponse:
    if not settings.openai_api_key:
        return _mock_response()

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
        return VisionAnalysisResponse(**data)
    except Exception as e:
        print(f"[VisionService] Error: {e}")
        return _mock_response()


def _mock_response() -> VisionAnalysisResponse:
    """Fallback when OpenAI is unavailable — returns plausible demo data."""
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
