"""Validated image uploads: size, magic-byte MIME, UUID filenames, EXIF strip.

Persistent storage
------------------
When GCS_BUCKET_NAME is set, ``persist_upload`` uploads to Google Cloud Storage
and returns a public ``https://storage.googleapis.com/...`` URL.

The bucket must have the ``allUsers`` principal granted
``roles/storage.objectViewer`` (uniform bucket-level access) so the URLs are
publicly readable without signed tokens.

When GCS_BUCKET_NAME is not set, files are written to local disk (``./uploads``)
and the function returns a ``/uploads/<filename>`` relative URL — suitable for
local development only, not persistent across container restarts.

GCS credentials
---------------
1. Set ``GCS_CREDENTIALS_JSON`` to the full service-account JSON string.
2. Or set ``GOOGLE_APPLICATION_CREDENTIALS`` to the path of the JSON key file.
3. Or leave both unset to use Application Default Credentials (Cloud Run, GKE, etc.).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import BadRequestError

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

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

_GCS_UPLOADS_PREFIX = "uploads"


# ── Image validation ──────────────────────────────────────────────────────────

def _detect_image_type(header: bytes) -> Optional[str]:
    if len(header) < 12:
        return None
    if header.startswith(ALLOWED_MIME_SIGNATURES["image/jpeg"][0]):
        return "image/jpeg"
    if header.startswith(ALLOWED_MIME_SIGNATURES["image/png"][0]):
        return "image/png"
    if (
        header[0:4] == ALLOWED_MIME_SIGNATURES["image/webp"][0]
        and header[8:12] == ALLOWED_MIME_SIGNATURES["image/webp"][1]
    ):
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
        raise BadRequestError(
            "Invalid file type. Only JPEG, PNG, and WebP images are accepted."
        )

    image_bytes = await file.read()
    if len(image_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise BadRequestError("File too large. Maximum size is 10MB.")

    image_bytes = strip_metadata(image_bytes, content_type)
    return image_bytes, content_type


# ── GCS helpers ───────────────────────────────────────────────────────────────

def _gcs_client():
    """Build a GCS Storage client from settings credentials or ADC."""
    try:
        from google.cloud import storage  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "google-cloud-storage is not installed. "
            "Add it to requirements.txt: google-cloud-storage>=2.16.0"
        )

    settings = get_settings()
    creds_json = settings.gcs_credentials_json

    if creds_json:
        try:
            from google.oauth2 import service_account  # type: ignore[import-untyped]

            creds_dict = json.loads(creds_json)
            project = settings.gcs_project_id or creds_dict.get("project_id")
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return storage.Client(project=project, credentials=credentials)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to build GCS client from GCS_CREDENTIALS_JSON: {exc}"
            ) from exc

    # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS, workload identity, etc.)
    return storage.Client(project=settings.gcs_project_id or None)


def _gcs_upload(image_bytes: bytes, blob_name: str, content_type: str) -> str:
    """Upload bytes to GCS and return the public HTTPS URL.

    The bucket must have allUsers / roles/storage.objectViewer for public reads.
    """
    settings = get_settings()
    client = _gcs_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=content_type)
    return f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{blob_name}"


# ── Public API ────────────────────────────────────────────────────────────────

def persist_upload(
    image_bytes: bytes, content_type: str, original_filename: Optional[str]
) -> str:
    """Persist image bytes and return a stable public URL.

    Returns a ``https://storage.googleapis.com/...`` URL when GCS is configured,
    or a ``/uploads/<filename>`` relative URL for local-disk fallback.
    """
    settings = get_settings()
    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = MIME_TO_SUFFIX.get(content_type, ".jpg")
    stored_name = f"{uuid4()}{suffix}"

    if settings.gcs_enabled:
        blob_name = f"{_GCS_UPLOADS_PREFIX}/{stored_name}"
        return _gcs_upload(image_bytes, blob_name, content_type)

    # Local fallback — development only, not persistent across container restarts
    root = settings.upload_path
    dest = root / stored_name
    dest.write_bytes(image_bytes)
    return f"/uploads/{stored_name}"


def read_upload_bytes(url: str) -> bytes:
    """Read image bytes from GCS or local disk based on the stored URL.

    Handles both:
    - GCS URLs: ``https://storage.googleapis.com/{bucket}/{blob}``
    - Local URLs: ``/uploads/{filename}``
    """
    settings = get_settings()

    if url.startswith("https://storage.googleapis.com/"):
        # URL format: https://storage.googleapis.com/{bucket}/{blob_path}
        without_prefix = url.removeprefix("https://storage.googleapis.com/")
        parts = without_prefix.split("/", 1)
        if len(parts) != 2:
            raise BadRequestError(f"Malformed GCS URL: {url}")
        blob_name = parts[1]
        client = _gcs_client()
        bucket = client.bucket(settings.gcs_bucket_name)
        return bucket.blob(blob_name).download_as_bytes()

    # Local path like /uploads/uuid.jpg
    img_path = settings.upload_path / Path(url).name
    if not img_path.exists():
        raise BadRequestError(f"Source image file not found: {img_path.name}")
    return img_path.read_bytes()
