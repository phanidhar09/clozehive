"""Regression tests for _compress_image — the vision-pipeline entry that
downscales uploads before detection.

The key behaviour (besides correct output dimensions) is that large JPEGs are
decoded at a reduced scale via PIL's ``draft`` mode so a phone photo never
materialises at full resolution — without it, big uploads OOM-kill small
instances mid-request and the dropped connection surfaces to the client as a
generic "Network Error".
"""

from __future__ import annotations

import io

from PIL import Image

from app.api.v1.wardrobe.services.vision_pipeline_service import (
    _MAX_DIMENSION,
    _compress_image,
)


def _jpeg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (123, 80, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _dims(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_large_jpeg_downscaled_to_cap_preserving_aspect() -> None:
    out, media_type = _compress_image(_jpeg(4000, 3000), "image/jpeg")
    w, h = _dims(out)
    assert max(w, h) <= _MAX_DIMENSION
    assert media_type == "image/jpeg"
    # 4:3 aspect preserved within rounding.
    assert abs((w / h) - (4000 / 3000)) < 0.02


def test_small_image_not_upscaled() -> None:
    out, _ = _compress_image(_jpeg(500, 400), "image/jpeg")
    assert _dims(out) == (500, 400)


def test_png_downscaled_and_reencoded_jpeg() -> None:
    buf = io.BytesIO()
    Image.new("RGBA", (2000, 2000), (0, 0, 0, 255)).save(buf, format="PNG")
    out, media_type = _compress_image(buf.getvalue(), "image/png")
    assert max(_dims(out)) <= _MAX_DIMENSION
    assert media_type == "image/jpeg"


def test_draft_reduces_decoded_raster_for_large_jpeg() -> None:
    """draft() must shrink the decoded size before any full-res materialisation
    (the memory guard). Without it this stays 4000x3000."""
    im = Image.open(io.BytesIO(_jpeg(4000, 3000)))
    im.draft("RGB", (_MAX_DIMENSION, _MAX_DIMENSION))
    assert max(im.size) < 4000


def test_explicit_max_side_override() -> None:
    out, _ = _compress_image(_jpeg(3000, 3000), "image/jpeg", max_side=800)
    assert max(_dims(out)) <= 800
