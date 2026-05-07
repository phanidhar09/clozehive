import pytest


@pytest.mark.asyncio
async def test_generate_outfits_falls_back_when_ai_raises(monkeypatch):
    async def boom(*_a, **_kw):
        raise RuntimeError("openai unavailable")

    monkeypatch.setattr("app.services.ai_service.chat", boom)
    from app.services.outfit_service import generate_outfits

    closet = [{"id": "a", "name": "Blue Tee", "category": "tops"}]
    result = await generate_outfits(closet, "casual")
    assert "outfits" in result
    assert len(result["outfits"]) >= 1


@pytest.mark.asyncio
async def test_packing_fallback_on_bad_dates():
    from app.services.packing_service import generate_packing_list

    result = await generate_packing_list("Paris", "not-a-date", "2024-01-05", "leisure", [])
    assert result["destination"] == "Paris"
    assert result.get("packing_list")
