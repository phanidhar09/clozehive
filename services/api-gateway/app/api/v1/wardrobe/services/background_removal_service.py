"""
Background removal service — solid-BG PIL + optional rembg for complex scenes.

Priority chain
--------------
1. rembg (ONNX U2Net)  — handles any background reliably if the package is installed.
2. PIL corner-sampling  — fast, zero extra deps, works on solid/studio backgrounds.
3. Original image       — returned as PNG when both methods fail or are skipped.

Why rembg is optional
---------------------
rembg pulls in ~170 MB of ONNX weights on first use and requires PyTorch/onnxruntime.
To keep containers lean in environments that don't need it, we import it lazily.
Install with:  pip install rembg>=2.0.50

Async helpers
-------------
Both PIL and rembg are CPU-bound.  Call ``remove_background_async()`` from async
code — it runs the sync function on the default thread-pool executor via
``asyncio.to_thread`` so the event loop stays unblocked.

Return type
-----------
All public functions return (processed_bytes: bytes, status: str) where status is
one of:
  "success_rembg"  — rembg succeeded
  "success_pil"    — PIL corner-sampling succeeded
  "skipped"        — BG was too complex for PIL and rembg is not installed
  "failed"         — an error occurred in both methods
"""

from __future__ import annotations

import asyncio
import io
import math
import statistics

from PIL import Image, ImageFilter

from app.core.logging import get_logger

logger = get_logger("background_removal")

# Public type alias for the return value
BgResult = tuple[bytes, str]  # (image_bytes, status)

# ── Tuning constants ───────────────────────────────────────────────────────────

_CORNER_PATCH = 6
_DEFAULT_TOLERANCE = 45
_UNIFORMITY_THRESHOLD = 0.50


# ── rembg detection ────────────────────────────────────────────────────────────


def _try_rembg(image_bytes: bytes) -> bytes | None:
    """
    Attempt background removal using rembg (ONNX U2Net).
    Returns RGBA PNG bytes on success, None if rembg is unavailable or fails.
    """
    try:
        import rembg  # type: ignore[import]

        result = rembg.remove(image_bytes)
        if result:
            logger.debug("rembg_success", size_kb=round(len(result) / 1024, 1))
            return result
    except ImportError:
        pass  # rembg not installed — silently fall through to PIL
    except Exception as exc:
        logger.warning("rembg_failed", error=str(exc))
    return None


# ── PIL corner-sampling helpers ────────────────────────────────────────────────


def _sample_bg_colour(img: Image.Image) -> tuple[int, int, int]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = _CORNER_PATCH
    r_vals: list[int] = []
    g_vals: list[int] = []
    b_vals: list[int] = []
    for x0, y0 in [(0, 0), (w - patch, 0), (0, h - patch), (w - patch, h - patch)]:
        for dx in range(patch):
            for dy in range(patch):
                r, g, b = rgb.getpixel((min(x0 + dx, w - 1), min(y0 + dy, h - 1)))  # type: ignore[misc]
                r_vals.append(r)
                g_vals.append(g)
                b_vals.append(b)
    return int(statistics.median(r_vals)), int(statistics.median(g_vals)), int(statistics.median(b_vals))


def _colour_distance(r: int, g: int, b: int, ref: tuple[int, int, int]) -> float:
    return math.sqrt((r - ref[0]) ** 2 + (g - ref[1]) ** 2 + (b - ref[2]) ** 2)


def _bg_uniformity(img: Image.Image, bg: tuple[int, int, int], tolerance: int) -> float:
    rgb = img.convert("RGB")
    w, h = rgb.size
    patch = 8
    match = total = 0
    for x0, y0 in [(0, 0), (w - patch, 0), (0, h - patch), (w - patch, h - patch)]:
        for dx in range(patch):
            for dy in range(patch):
                r, g, b = rgb.getpixel((min(x0 + dx, w - 1), min(y0 + dy, h - 1)))  # type: ignore[misc]
                if _colour_distance(r, g, b, bg) < tolerance:
                    match += 1
                total += 1
    return match / total if total else 0.0


def _adaptive_tolerance(bg: tuple[int, int, int], base: int) -> int:
    brightness = sum(bg) / 3
    if brightness > 220:
        return max(base, 60)
    if brightness > 180:
        return max(base, 50)
    if brightness < 50:
        return max(base, 55)
    return base


def _pil_remove(image_bytes: bytes, base_tolerance: int = _DEFAULT_TOLERANCE) -> bytes | None:
    """
    PIL corner-sampling background removal.
    Returns RGBA PNG bytes if the background is uniform enough, else None.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        bg = _sample_bg_colour(img)
        tolerance = _adaptive_tolerance(bg, base_tolerance)
        uniformity = _bg_uniformity(img, bg, tolerance)

        if uniformity < _UNIFORMITY_THRESHOLD:
            logger.debug("pil_bg_skip", uniformity=round(uniformity, 3))
            return None

        rgba_pixels = list(img.getdata())
        new_pixels: list[tuple[int, int, int, int]] = []
        for pixel in rgba_pixels:
            r, g, b = pixel[0], pixel[1], pixel[2]
            dist = _colour_distance(r, g, b, bg)
            if dist < tolerance:
                raw_alpha = int(min(255, (dist / tolerance) * 255 * 1.8))
                new_pixels.append((r, g, b, raw_alpha))
            else:
                new_pixels.append((r, g, b, 255))
        img.putdata(new_pixels)  # type: ignore[arg-type]

        r_ch, g_ch, b_ch, a_ch = img.split()
        a_ch = a_ch.filter(ImageFilter.GaussianBlur(radius=1.5))
        a_ch = a_ch.point(lambda p: 255 if p > 200 else p)
        img = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        result = buf.getvalue()
        logger.debug("pil_bg_success", uniformity=round(uniformity, 3), tolerance=tolerance)
        return result
    except Exception as exc:
        logger.warning("pil_bg_error", error=str(exc))
        return None


def _as_png(image_bytes: bytes) -> bytes:
    """Convert any image to PNG (RGBA). Used for the fallback path."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes


# ── Public sync API ────────────────────────────────────────────────────────────


def remove_background(image_bytes: bytes, base_tolerance: int = _DEFAULT_TOLERANCE) -> bytes:
    """
    Legacy single-return wrapper (backward compatible).
    Returns processed PNG bytes — may or may not have BG removed.
    """
    processed, _ = remove_background_with_status(image_bytes, base_tolerance)
    return processed


def remove_background_with_status(
    image_bytes: bytes,
    base_tolerance: int = _DEFAULT_TOLERANCE,
) -> BgResult:
    """
    Remove background and report whether it succeeded.

    Returns (processed_bytes, status) where status is one of:
      "success_rembg" | "success_pil" | "skipped" | "failed"

    Never raises — all errors return ("failed", original_bytes_as_png).
    """
    try:
        # 1. Try rembg first — handles any background type
        rembg_result = _try_rembg(image_bytes)
        if rembg_result is not None:
            return rembg_result, "success_rembg"

        # 2. Fall back to PIL corner-sampling for solid/near-solid BGs
        pil_result = _pil_remove(image_bytes, base_tolerance)
        if pil_result is not None:
            return pil_result, "success_pil"

        # 3. Background too complex and rembg not available — return original as PNG
        logger.info("bg_removal_skipped", reason="complex_bg_no_rembg")
        return _as_png(image_bytes), "skipped"

    except Exception as exc:
        logger.error("bg_removal_critical_error", error=str(exc))
        return _as_png(image_bytes), "failed"


# ── Public async API ───────────────────────────────────────────────────────────


async def remove_background_async(
    image_bytes: bytes,
    base_tolerance: int = _DEFAULT_TOLERANCE,
) -> BgResult:
    """
    Async wrapper — runs the CPU-bound removal on the thread pool so the
    event loop stays unblocked during concurrent processing.
    """
    return await asyncio.to_thread(remove_background_with_status, image_bytes, base_tolerance)


def to_png(image_bytes: bytes) -> bytes:
    """Convert any image to PNG without background removal."""
    return _as_png(image_bytes)
