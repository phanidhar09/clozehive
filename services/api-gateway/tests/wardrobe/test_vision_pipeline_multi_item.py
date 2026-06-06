"""
Tests for multi-item vision pipeline detected_item_id correctness.

Verifies that every detected clothing item receives its own stable
detected_item_id, a unique crop, and that metadata stays bound to the
correct item — even when multiple items share the same source image.
"""

from __future__ import annotations

import asyncio
import base64
import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from PIL import Image

from app.api.v1.wardrobe.schemas.closet import VisionAnalysisItem, VisionAnalyzeResponse


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_1px_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 400), color=(120, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_detection_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items}


_SHIRT_RAW = {
    "item_id": "shirt-raw-1",
    "category": "tops",
    "subcategory": "shirt",
    "primary_color": "black",
    "description": "Black cotton shirt",
    "detection_confidence": 0.92,
    "bbox": {"x_min": 0.05, "y_min": 0.05, "x_max": 0.95, "y_max": 0.45},
}

_PANTS_RAW = {
    "item_id": "pants-raw-1",
    "category": "bottoms",
    "subcategory": "jeans",
    "primary_color": "blue",
    "description": "Blue denim jeans",
    "detection_confidence": 0.88,
    "bbox": {"x_min": 0.10, "y_min": 0.50, "x_max": 0.90, "y_max": 0.95},
}


async def _run_pipeline(raw_items: list[dict], image_bytes: bytes) -> VisionAnalyzeResponse:
    """Run the real pipeline with mocked IO (no BG removal, no Redis, no enrichment)."""
    from app.api.v1.wardrobe.services.vision_pipeline_service import run_pipeline

    with (
        patch("app.api.v1.wardrobe.services.vision_pipeline_service._cache_get", AsyncMock(return_value=None)),
        patch("app.api.v1.wardrobe.services.vision_pipeline_service._cache_set", AsyncMock()),
        patch(
            "app.api.v1.wardrobe.services.vision_pipeline_service._run_detection",
            AsyncMock(return_value=_fake_detection_result(raw_items)),
        ),
        patch(
            "app.api.v1.wardrobe.services.vision_pipeline_service._remove_bg_timed",
            AsyncMock(return_value=(image_bytes, "success_rembg")),
        ),
        patch(
            "app.api.v1.wardrobe.services.vision_pipeline_service.enrich_detection_with_crop_analysis",
            AsyncMock(side_effect=lambda _bytes, d: d),
        ),
    ):
        return await run_pipeline(image_bytes, "image/jpeg", "scan-test", preview_fast=False)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestSingleItemPipeline:
    @pytest.mark.asyncio
    async def test_single_item_returns_one_item(self):
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW], img)
        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_single_item_has_detected_item_id(self):
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW], img)
        item = result.items[0]
        assert item.detected_item_id
        # Must be a valid UUID v4.
        UUID(item.detected_item_id)

    @pytest.mark.asyncio
    async def test_single_item_has_image_base64(self):
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW], img)
        item = result.items[0]
        assert item.image_base64
        # Should be decodable.
        decoded = base64.b64decode(item.image_base64)
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_single_item_missing_bbox_falls_back_to_full_frame(self):
        """Single-item detection without bbox should succeed using the full image."""
        img = _make_1px_jpeg()
        raw_no_bbox = {**_SHIRT_RAW}
        raw_no_bbox.pop("bbox", None)
        result = await _run_pipeline([raw_no_bbox], img)
        assert len(result.items) == 1
        assert result.failed_items == []


class TestMultiItemPipeline:
    @pytest.mark.asyncio
    async def test_two_items_return_two_items(self):
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW, _PANTS_RAW], img)
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_each_item_gets_unique_detected_item_id(self):
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW, _PANTS_RAW], img)
        ids = [it.detected_item_id for it in result.items]
        assert ids[0] != ids[1], "detected_item_id must be unique per item"
        for did in ids:
            UUID(did)  # must be valid UUID

    @pytest.mark.asyncio
    async def test_metadata_stays_with_correct_item(self):
        """shirt metadata must not appear on pants item and vice versa."""
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW, _PANTS_RAW], img)
        by_category = {it.category: it for it in result.items}
        assert "tops" in by_category
        assert "bottoms" in by_category
        assert by_category["tops"].primary_color == "black"
        assert by_category["bottoms"].primary_color == "blue"

    @pytest.mark.asyncio
    async def test_each_item_has_unique_image_base64(self):
        """When BG-removal returns distinct bytes per call, image_base64 must differ."""
        img = _make_1px_jpeg()

        # Give each BG removal call distinct output bytes so we can verify no sharing.
        shirt_bytes = b"shirt-crop-bytes"
        pants_bytes = b"pants-crop-bytes"
        call_count = {"n": 0}

        async def fake_bg(crop_bytes: bytes) -> tuple[bytes, str]:
            call_count["n"] += 1
            return (shirt_bytes if call_count["n"] == 1 else pants_bytes), "success_rembg"

        with (
            patch("app.api.v1.wardrobe.services.vision_pipeline_service._cache_get", AsyncMock(return_value=None)),
            patch("app.api.v1.wardrobe.services.vision_pipeline_service._cache_set", AsyncMock()),
            patch(
                "app.api.v1.wardrobe.services.vision_pipeline_service._run_detection",
                AsyncMock(return_value=_fake_detection_result([_SHIRT_RAW, _PANTS_RAW])),
            ),
            patch("app.api.v1.wardrobe.services.vision_pipeline_service._remove_bg_timed", fake_bg),
            patch(
                "app.api.v1.wardrobe.services.vision_pipeline_service.enrich_detection_with_crop_analysis",
                AsyncMock(side_effect=lambda _b, d: d),
            ),
        ):
            from app.api.v1.wardrobe.services.vision_pipeline_service import run_pipeline
            result = await run_pipeline(img, "image/jpeg", "scan-multi", preview_fast=False)

        assert len(result.items) == 2
        b64s = [it.image_base64 for it in result.items]
        assert b64s[0] != b64s[1], "Each item must have a distinct image_base64"

    @pytest.mark.asyncio
    async def test_failed_crop_one_item_does_not_fail_all(self):
        """If one item's bbox is missing in multi-item mode, only that item fails."""
        img = _make_1px_jpeg()
        # Remove bbox from shirt — should fail individually.
        shirt_no_bbox = {**_SHIRT_RAW}
        shirt_no_bbox.pop("bbox", None)

        result = await _run_pipeline([shirt_no_bbox, _PANTS_RAW], img)

        # Pants should still succeed.
        assert len(result.items) == 1
        assert result.items[0].category == "bottoms"
        # Shirt should be in failed_items.
        assert len(result.failed_items) == 1
        assert result.failed_items[0]["detected_item_id"]

    @pytest.mark.asyncio
    async def test_detected_item_id_differs_from_ai_item_id(self):
        """detected_item_id is always a fresh UUID, not the AI-provided item_id."""
        img = _make_1px_jpeg()
        result = await _run_pipeline([_SHIRT_RAW, _PANTS_RAW], img)
        for item in result.items:
            # AI provided "shirt-raw-1" / "pants-raw-1" — detected_item_id must be different.
            assert item.detected_item_id not in ("shirt-raw-1", "pants-raw-1")

    @pytest.mark.asyncio
    async def test_no_shared_mutable_state_between_items(self):
        """All three items must have distinct detected_item_ids (stress test for closure capture)."""
        img = _make_1px_jpeg()
        third = {
            **_PANTS_RAW,
            "item_id": "shoes-raw-1",
            "category": "shoes",
            "primary_color": "white",
            "bbox": {"x_min": 0.20, "y_min": 0.80, "x_max": 0.80, "y_max": 0.99},
        }
        result = await _run_pipeline([_SHIRT_RAW, _PANTS_RAW, third], img)
        # All successful (all have valid bboxes).
        assert len(result.items) + len(result.failed_items) == 3
        ids = [it.detected_item_id for it in result.items]
        assert len(set(ids)) == len(ids), "All detected_item_ids must be unique"


class TestCacheHitRecrop:
    """Validate that analyze_preview re-crops from source bytes on pipeline cache hits."""

    @pytest.mark.asyncio
    async def test_cache_hit_triggers_recrop_not_original_url(self):
        """On a cache hit (image_base64=None), each item must get its own crop URL."""
        from app.api.v1.wardrobe.services.closet_preview_service import analyze_preview
        from app.api.v1.wardrobe.schemas.closet import NormalizedBoundingBox, VisionAnalysisItem, VisionAnalyzeResponse

        img = _make_1px_jpeg()

        # Simulate a cached pipeline response: image_base64 is absent.
        shirt_item = VisionAnalysisItem(
            detected_item_id="did-shirt-123",
            item_id="did-shirt-123",
            name="Black Shirt",
            category="tops",
            primary_color="black",
            confidence_score=0.91,
            image_base64=None,
            processed_image=None,
            bounding_box=NormalizedBoundingBox(x=0.05, y=0.05, width=0.90, height=0.40),
            background_removal_status="cache_hit",
        )
        pants_item = VisionAnalysisItem(
            detected_item_id="did-pants-456",
            item_id="did-pants-456",
            name="Blue Jeans",
            category="bottoms",
            primary_color="blue",
            confidence_score=0.88,
            image_base64=None,
            processed_image=None,
            bounding_box=NormalizedBoundingBox(x=0.10, y=0.50, width=0.80, height=0.45),
            background_removal_status="cache_hit",
        )

        cached_pipeline = VisionAnalyzeResponse(
            scan_id="scan-cached",
            total_items_detected=2,
            items=[shirt_item, pants_item],
            processing_time_ms=10,
            cached=True,
        )

        persisted_urls: list[str] = []

        def fake_persist(image_bytes: bytes, content_type: str, filename: str | None) -> str:
            url = f"/uploads/fake-{len(persisted_urls)}.png"
            persisted_urls.append(url)
            return url

        with (
            patch("app.api.v1.wardrobe.services.closet_preview_service.run_pipeline", AsyncMock(return_value=cached_pipeline)),
            patch("app.api.v1.wardrobe.services.closet_preview_service.persist_upload", side_effect=fake_persist),
            patch("app.core.cache_service.set", AsyncMock(return_value=True)),
        ):
            response = await analyze_preview(
                user_id=__import__("uuid").uuid4(),
                image_bytes=img,
                content_type="image/jpeg",
                filename="outfit.jpg",
            )

        # Two items → should each be re-cropped → two distinct crop URLs.
        assert len(response.items) == 2
        urls = [it.processed_image_url for it in response.items]
        assert urls[0] != urls[1], (
            "Cache-hit items must each get a unique re-cropped URL, not both fall back to original"
        )
        # Neither should equal the original_image_url.
        original = response.items[0].original_image_url
        for url in urls:
            assert url != original, "processed_image_url must not be the original (full) image"
