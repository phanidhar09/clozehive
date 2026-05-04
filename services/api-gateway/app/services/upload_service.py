"""Validated image uploads: size, magic-byte MIME, UUID filenames, EXIF strip."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import BadRequestError

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

ALLOWED_MIME_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF", b"WEBP"),
}

MIME_TO_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _detect_image_type(header: bytes) -> Optional[str]:
    if len(header) < 12:
        return None
    if header.startswith(ALLOWED_MIME_SIGNATURES["image/jpeg"][0]):
        return "image/jpeg"
    if header.startswith(ALLOWED_MIME_SIGNATURES["image/png"][0]):
        return "image/png"
    if header[0:4] == ALLOWED_MIME_SIGNATURES["image/webp"][0] and header[8:12] == ALLOWED_MIME_SIGNATURES["image/webp"][1]:
        return "image/webp"
    return None


def strip_metadata(image_bytes: bytes, content_type: str) -> bytes:
    """Re-encode image to drop EXIF and validate pixels (best-effort)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return image_bytes

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        buf = io.BytesIO()
        if content_type == "image/jpeg":
            rgb = img.convert("RGB")
            rgb.save(buf, format="JPEG", quality=90, optimize=True)
        elif content_type == "image/png":
            img.save(buf, format="PNG", optimize=True)
        elif content_type == "image/webp":
            rgb = img.convert("RGBA") if img.mode in ("RGBA", "P") else img.convert("RGB")
            rgb.save(buf, format="WEBP", quality=85, method=6)
        else:
            return image_bytes
        out = buf.getvalue()
        if len(out) > MAX_UPLOAD_SIZE_BYTES:
            raise BadRequestError("Processed image exceeds 10MB. Try a smaller photo.")
        return out
    except BadRequestError:
        raise
    except Exception:
        return image_bytes


async def read_validated_image(file: UploadFile) -> tuple[bytes, str]:
    """Read upload bytes, enforce size and JPEG/PNG/WebP via magic bytes."""
    if file.size is not None and file.size > MAX_UPLOAD_SIZE_BYTES:
        raise BadRequestError("File too large. Maximum size is 10MB.")

    header = await file.read(12)
    await file.seek(0)
    content_type = _detect_image_type(header)
    if not content_type:
        raise BadRequestError("Invalid file type. Only JPEG, PNG, and WebP images are accepted.")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise BadRequestError("File too large. Maximum size is 10MB.")

    image_bytes = strip_metadata(image_bytes, content_type)
    return image_bytes, content_type


def persist_upload(image_bytes: bytes, content_type: str, original_filename: Optional[str]) -> str:
    """Write to disk with random UUID name and allowed extension."""
    root = get_settings().upload_path
    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = MIME_TO_SUFFIX.get(content_type, ".jpg")
    stored_name = f"{uuid4()}{suffix}"
    dest = root / stored_name
    dest.write_bytes(image_bytes)
    return f"/uploads/{stored_name}"
