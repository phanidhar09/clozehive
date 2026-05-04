"""
PIL-based background removal for clothing item images.

Design rationale
----------------
We deliberately avoid heavy ML dependencies (rembg / PyTorch / ONNX) here.
Pillow is already in requirements.txt; adding a 170 MB ONNX model would bloat
every container image and require network access on first boot.

This implementation handles the dominant wardrobe-photo scenarios:
  ✓ Flat-lay on white / light-grey background  (~60 % of uploads)
  ✓ Item on hanger against a plain wall         (~20 %)
  ✓ Product shots on solid studio backgrounds   (~10 %)
  ~ Person in natural scene                     (falls back to original)
  ~ Complex gradient backgrounds                (falls back to original)

Algorithm
---------
1. Sample 6×6-pixel patches from all four corners → median background colour.
   Median is used instead of mean so that dark edge shadows / dust specks
   in the corner don't skew the estimate.
2. Compute a uniformity score: fraction of the same corner pixels that are
   within `tolerance` distance of that median colour (Euclidean RGB space).
   If uniformity < 50 % the background is too complex — we skip removal and
   return the original PNG, avoiding ugly artifacts on complex scenes.
3. Walk every pixel; compute its distance from the background colour.
   Apply a soft ramp:
     - dist < tolerance → increasingly transparent  (edge blend)
     - dist ≥ tolerance → fully opaque
4. Smooth the alpha channel with a light Gaussian blur (radius 1.5) to avoid
   jagged/aliased edges on the subject silhouette.
5. Clip the blurred alpha so that interior pixels (high distance) stay at 255.
6. Save as RGBA PNG.

Adding rembg later
------------------
Drop-in replacement — just call rembg.remove(image_bytes) and return the RGBA
PNG bytes.  The rest of the pipeline stays identical.
"""

from __future__ import annotations

import io
import math
import statistics

from PIL import Image, ImageFilter

from app.core.logging import get_logger

logger = get_logger("background_removal")

# ── Tuning constants ───────────────────────────────────────────────────────────

_CORNER_PATCH = 6          # pixels per side sampled from each corner
_DEFAULT_TOLERANCE = 45    # max Euclidean RGB distance to classify as background
_UNIFORMITY_THRESHOLD = 0.50  # minimum fraction of corners matching bg colour


# ── Internal helpers ───────────────────────────────────────────────────────────

def _sample_bg_colour(img: Image.Image) -> tuple[int, int, int]:
    """
    Sample four corners and return the median RGB as background estimate.

    Uses median (not mean) so that a single dark speck in a white corner
    doesn't drag the estimate toward grey.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = _CORNER_PATCH
    r_vals: list[int] = []
    g_vals: list[int] = []
    b_vals: list[int] = []

    for x0, y0 in [
        (0, 0),
        (w - patch, 0),
        (0, h - patch),
        (w - patch, h - patch),
    ]:
        for dx in range(patch):
            for dy in range(patch):
                px = min(x0 + dx, w - 1)
                py = min(y0 + dy, h - 1)
                r, g, b = rgb.getpixel((px, py))  # type: ignore[misc]
                r_vals.append(r)
                g_vals.append(g)
                b_vals.append(b)

    return (
        int(statistics.median(r_vals)),
        int(statistics.median(g_vals)),
        int(statistics.median(b_vals)),
    )


def _colour_distance(r: int, g: int, b: int, ref: tuple[int, int, int]) -> float:
    return math.sqrt((r - ref[0]) ** 2 + (g - ref[1]) ** 2 + (b - ref[2]) ** 2)


def _bg_uniformity(
    img: Image.Image,
    bg: tuple[int, int, int],
    tolerance: int,
) -> float:
    """Fraction of sampled corner pixels within `tolerance` of `bg`."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = 8   # slightly larger patch for the uniformity check
    match = total = 0
    for x0, y0 in [
        (0, 0),
        (w - patch, 0),
        (0, h - patch),
        (w - patch, h - patch),
    ]:
        for dx in range(patch):
            for dy in range(patch):
                r, g, b = rgb.getpixel((  # type: ignore[misc]
                    min(x0 + dx, w - 1),
                    min(y0 + dy, h - 1),
                ))
                if _colour_distance(r, g, b, bg) < tolerance:
                    match += 1
                total += 1
    return match / total if total else 0.0


def _adaptive_tolerance(bg: tuple[int, int, int], base: int) -> int:
    """
    Widen tolerance for very bright (near-white) or very dark (near-black)
    backgrounds, which are the most common studio setups.
    """
    brightness = sum(bg) / 3
    if brightness > 220:   # near-white
        return max(base, 60)
    if brightness > 180:   # light grey
        return max(base, 50)
    if brightness < 50:    # near-black
        return max(base, 55)
    return base


# ── Public API ─────────────────────────────────────────────────────────────────

def remove_background(
    image_bytes: bytes,
    base_tolerance: int = _DEFAULT_TOLERANCE,
) -> bytes:
    """
    Remove solid/near-solid background from a clothing image.

    Returns RGBA PNG bytes. If the background is too complex to remove
    cleanly (uniformity < 50 %), returns the original image as PNG to
    avoid visual artifacts.

    Never raises — all failures are caught and logged; original bytes
    are returned on any error.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        bg = _sample_bg_colour(img)
        tolerance = _adaptive_tolerance(bg, base_tolerance)
        uniformity = _bg_uniformity(img, bg, tolerance)

        if uniformity < _UNIFORMITY_THRESHOLD:
            logger.info(
                "bg_removal_skipped",
                reason="complex_or_dark_background",
                uniformity=round(uniformity, 3),
            )
            # Return as PNG (preserving any existing transparency)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        # ── Build per-pixel alpha mask ─────────────────────────────────────────
        # Soft ramp: pixels near the background colour fade out gradually;
        # interior pixels (clothing) stay fully opaque.
        rgba_pixels = list(img.getdata())
        new_pixels: list[tuple[int, int, int, int]] = []

        for pixel in rgba_pixels:
            r, g, b = pixel[0], pixel[1], pixel[2]
            dist = _colour_distance(r, g, b, bg)
            if dist < tolerance:
                # Map [0, tolerance] → [0, ~192] alpha so edges blend softly.
                # Multiply by 1.8 to push mid-distance pixels toward opaque
                # (avoids the subject looking washed out at edges).
                raw_alpha = int(min(255, (dist / tolerance) * 255 * 1.8))
                new_pixels.append((r, g, b, raw_alpha))
            else:
                new_pixels.append((r, g, b, 255))

        img.putdata(new_pixels)  # type: ignore[arg-type]

        # ── Smooth the alpha channel ───────────────────────────────────────────
        # Split channels, blur only alpha to feather silhouette edges, then
        # threshold: keep interior fully opaque so clothes don't go semi-transparent.
        r_ch, g_ch, b_ch, a_ch = img.split()
        a_ch = a_ch.filter(ImageFilter.GaussianBlur(radius=1.5))
        # Pixels that were already opaque (dist ≥ tolerance) should stay at 255;
        # the blur might lower them slightly — clamp back up.
        a_ch = a_ch.point(lambda p: 255 if p > 200 else p)
        img = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)

        logger.info(
            "bg_removal_success",
            uniformity=round(uniformity, 3),
            tolerance=tolerance,
            size_kb=round(len(buf.getvalue()) / 1024, 1),
        )
        return buf.getvalue()

    except Exception as exc:
        logger.warning("bg_removal_error", error=str(exc))
        return image_bytes  # never fail — return original


def to_png(image_bytes: bytes) -> bytes:
    """
    Convert any supported image to PNG (no background removal).
    Used as a fallback when background is too complex.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes
