"""Unit tests for gemini_service pure helpers — no network, no Gemini SDK."""

from __future__ import annotations

from app.services.gemini_service import _bbox_iou, _clean_json, _deduplicate_items, is_available


def _bbox(x_min: float, y_min: float, x_max: float, y_max: float) -> dict[str, float]:
    return {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max}


class TestBboxIou:
    def test_identical_boxes(self) -> None:
        b = _bbox(0.1, 0.1, 0.5, 0.5)
        assert _bbox_iou(b, b) == 1.0

    def test_disjoint_boxes(self) -> None:
        assert _bbox_iou(_bbox(0.0, 0.0, 0.2, 0.2), _bbox(0.5, 0.5, 0.9, 0.9)) == 0.0

    def test_partial_overlap(self) -> None:
        iou = _bbox_iou(_bbox(0.0, 0.0, 0.5, 0.5), _bbox(0.25, 0.25, 0.75, 0.75))
        assert 0.0 < iou < 1.0

    def test_zero_area_boxes(self) -> None:
        degenerate = _bbox(0.3, 0.3, 0.3, 0.3)
        assert _bbox_iou(degenerate, degenerate) == 0.0


class TestDeduplicateItems:
    def test_same_category_high_overlap_keeps_higher_confidence(self) -> None:
        items = [
            {"category": "top", "detection_confidence": 0.6, "bbox": _bbox(0.1, 0.1, 0.5, 0.5)},
            {"category": "top", "detection_confidence": 0.9, "bbox": _bbox(0.1, 0.1, 0.5, 0.5)},
        ]
        kept = _deduplicate_items(items)
        assert len(kept) == 1
        assert kept[0]["detection_confidence"] == 0.9

    def test_different_categories_not_deduplicated(self) -> None:
        items = [
            {"category": "top", "detection_confidence": 0.9, "bbox": _bbox(0.1, 0.1, 0.5, 0.5)},
            {"category": "outerwear", "detection_confidence": 0.8, "bbox": _bbox(0.1, 0.1, 0.5, 0.5)},
        ]
        assert len(_deduplicate_items(items)) == 2

    def test_low_overlap_same_category_kept(self) -> None:
        items = [
            {"category": "footwear", "detection_confidence": 0.9, "bbox": _bbox(0.0, 0.8, 0.3, 1.0)},
            {"category": "footwear", "detection_confidence": 0.8, "bbox": _bbox(0.6, 0.8, 0.9, 1.0)},
        ]
        assert len(_deduplicate_items(items)) == 2

    def test_empty_list(self) -> None:
        assert _deduplicate_items([]) == []


class TestCleanJson:
    def test_strips_json_fence(self) -> None:
        assert _clean_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_bare_fence(self) -> None:
        assert _clean_json('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_json_untouched(self) -> None:
        assert _clean_json('  {"a": 1} ') == '{"a": 1}'


class TestIsAvailable:
    def test_empty_key_unavailable(self, monkeypatch) -> None:
        from app.services import gemini_service

        monkeypatch.setattr(gemini_service.settings, "gemini_api_key", "")
        assert gemini_service.is_available() is False

    def test_placeholder_key_unavailable(self, monkeypatch) -> None:
        from app.services import gemini_service

        monkeypatch.setattr(gemini_service.settings, "gemini_api_key", "your-gemini-api-key-goes-here")
        assert gemini_service.is_available() is False

    def test_realistic_key_available(self, monkeypatch) -> None:
        from app.services import gemini_service

        monkeypatch.setattr(gemini_service.settings, "gemini_api_key", "AIzaSyD4x9q8k2j3h5g7f1d0s9a8p7o6i5u4y3t")
        assert gemini_service.is_available() is True
