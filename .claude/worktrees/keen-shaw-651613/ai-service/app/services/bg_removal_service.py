"""
Background removal service — strips the background from clothing images.
Uses rembg (U-2-Net) when available; falls back to returning the original image.
"""
import base64
import io

from PIL import Image


def remove_background(image_bytes: bytes) -> tuple[str, str]:
    """
    Remove background from an image.

    Returns (base64_png, media_type) where base64_png is a base64-encoded PNG
    with transparent background, or the original image if removal fails.
    """
    try:
        from rembg import remove as rembg_remove

        output_bytes = rembg_remove(image_bytes)
        b64 = base64.b64encode(output_bytes).decode("utf-8")
        return b64, "image/png"
    except ImportError:
        pass
    except Exception as e:
        print(f"[BgRemoval] rembg failed: {e}")

    # Fallback: attempt a simple white-background removal using Pillow
    try:
        return _pillow_remove_white_bg(image_bytes)
    except Exception as e:
        print(f"[BgRemoval] Pillow fallback failed: {e}")

    # Last resort: return original image as-is
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return b64, "image/jpeg"


def _pillow_remove_white_bg(image_bytes: bytes, threshold: int = 230) -> tuple[str, str]:
    """
    Simple heuristic: make near-white pixels transparent.
    Works best for product photos on white/light backgrounds.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    data = img.getdata()

    new_data = []
    for r, g, b, a in data:
        # If the pixel is near-white, make it transparent
        if r > threshold and g > threshold and b > threshold:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append((r, g, b, a))

    img.putdata(new_data)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return b64, "image/png"
