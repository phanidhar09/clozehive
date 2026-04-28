"""
Vision MCP Server — port 8011
Analyses clothing images via GPT-4o Vision and returns structured metadata.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from shared.config import get_settings
from shared.health import health_payload
from shared.logger import get_logger
from service import analyse_image, encode_file

logger = get_logger("vision.server")
settings = get_settings()

mcp = FastMCP(
    name="clozehive-vision",
    instructions=(
        "Analyses clothing item images and returns structured fashion metadata. "
        "Input must be base64-encoded image data."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_TOOLS = ["analyze_clothing_image", "analyze_clothing_from_bytes"]


@mcp.tool()
async def analyze_clothing_image(image_base64: str, media_type: str = "image/jpeg") -> str:
    """
    Analyse a clothing item from a base64-encoded image.

    Args:
        image_base64: Base64-encoded image (with or without data-URL prefix).
        media_type:   Image MIME type — "image/jpeg" (default), "image/png", etc.

    Returns:
        JSON VisionAnalysisResult with: name, category, color, brand, material,
        pattern, occasion[], tags[], eco_score, confidence, notes.
    """
    if not image_base64.strip():
        return json.dumps({"error": "image_base64 cannot be empty"})

    logger.info("tool_analyze_clothing_image", media_type=media_type)
    try:
        result = await analyse_image(image_base64, media_type)
        return result.model_dump_json(indent=2)
    except Exception as exc:
        logger.error("tool_error", tool="analyze_clothing_image", error=str(exc))
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def analyze_clothing_from_bytes(
    image_bytes_hex: str,
    media_type: str = "image/jpeg",
) -> str:
    """
    Analyse a clothing item from hex-encoded raw image bytes.

    Args:
        image_bytes_hex: Hex-encoded raw image bytes.
        media_type:      Image MIME type.

    Returns:
        JSON VisionAnalysisResult (same structure as analyze_clothing_image).
    """
    if not image_bytes_hex.strip():
        return json.dumps({"error": "image_bytes_hex cannot be empty"})

    logger.info("tool_analyze_clothing_from_bytes", media_type=media_type)
    try:
        raw = bytes.fromhex(image_bytes_hex)
        b64 = encode_file(raw, media_type)
        result = await analyse_image(b64, media_type)
        return result.model_dump_json(indent=2)
    except ValueError:
        return json.dumps({"error": "invalid hex encoding"})
    except Exception as exc:
        logger.error("tool_error", tool="analyze_clothing_from_bytes", error=str(exc))
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    logger.info("vision_server_starting", port=settings.vision_port)
    mcp.settings.host = settings.vision_host
    mcp.settings.port = settings.vision_port
    mcp.run(transport="sse")
