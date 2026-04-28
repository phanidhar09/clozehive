"""
Vision MCP Server — port 8001
Exposes GPT-4o Vision garment analysis as an MCP tool.

Run:
    python server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP

from shared.config import get_settings
from shared.logger import get_logger
from service import analyse_image

logger = get_logger("vision.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-vision",
    instructions=(
        "Vision service for CLOZEHIVE. Analyses clothing item images using GPT-4o Vision "
        "and returns structured garment attributes: type, fabric, colour, pattern, season, "
        "occasion suitability, care instructions, eco score, and confidence level. "
        "Always pass a valid base64-encoded image string."
    ),
)


@mcp.tool()
async def analyze_garment_image(
    image_base64: str,
    media_type: str = "image/jpeg",
) -> str:
    """
    Analyse a clothing item image with GPT-4o Vision.

    Args:
        image_base64: Base64-encoded image bytes (no data-URL prefix needed).
                      Supported formats: JPEG, PNG, WebP, HEIC.
        media_type:   MIME type string, e.g. 'image/jpeg' or 'image/png'.
                      Defaults to 'image/jpeg'.

    Returns:
        JSON string — VisionAnalysisResult with fields:
          garment_type, fabric, color_primary, color_secondary, pattern,
          season, occasion[], care_instructions[], wearing_tips[],
          eco_score (1-10), confidence (0-1), raw_description.
    """
    logger.info("Tool: analyze_garment_image(media_type=%s, payload_len=%d)", media_type, len(image_base64))

    from shared.schemas import VisionAnalysisResult
    result: VisionAnalysisResult = await analyse_image(image_base64, media_type)
    return result.model_dump_json(indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting Vision MCP server on %s:%d",
        settings.vision_host,
        settings.vision_port,
    )
    mcp.run(
        transport="sse",
        host=settings.vision_host,
        port=settings.vision_port,
    )
