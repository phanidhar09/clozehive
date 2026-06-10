import pytest
from httpx import AsyncClient


async def headers_for(async_client: AsyncClient, prefix: str) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "name": f"{prefix} User",
            "email": f"{prefix}@example.com",
            "username": f"{prefix}user",
            "password": "Password1",
            "gdpr_consent": True,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_item(async_client: AsyncClient, headers: dict[str, str], name: str = "Blue Shirt") -> dict:
    response = await async_client.post(
        "/api/v1/closet/",
        headers=headers,
        json={"name": name, "category": "tops", "color": "blue"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_closet_item_returns_201(async_client: AsyncClient, auth_headers: dict[str, str]):
    response = await async_client.post(
        "/api/v1/closet/",
        headers=auth_headers,
        json={"name": "Black Jeans", "category": "bottoms", "color": "black"},
    )

    assert response.status_code == 201
    assert response.json()["id"]
    assert response.json()["name"] == "Black Jeans"


@pytest.mark.asyncio
async def test_get_closet_returns_only_own_items(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "closetusera")
    headers_b = await headers_for(async_client, "closetuserb")
    item_a = await create_item(async_client, headers_a, "Private Shirt")
    await create_item(async_client, headers_b, "Other Shirt")

    response = await async_client.get("/api/v1/closet/", headers=headers_a)

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert item_a["id"] in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_update_closet_item(async_client: AsyncClient, auth_headers: dict[str, str]):
    item = await create_item(async_client, auth_headers)
    response = await async_client.patch(
        f"/api/v1/closet/{item['id']}",
        headers=auth_headers,
        json={"name": "Updated Shirt"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Shirt"


@pytest.mark.asyncio
async def test_delete_closet_item(async_client: AsyncClient, auth_headers: dict[str, str]):
    item = await create_item(async_client, auth_headers)
    delete = await async_client.delete(f"/api/v1/closet/{item['id']}", headers=auth_headers)
    listing = await async_client.get("/api/v1/closet/", headers=auth_headers)

    assert delete.status_code == 204
    assert item["id"] not in {i["id"] for i in listing.json()["items"]}


@pytest.mark.asyncio
async def test_get_closet_item_by_id(async_client: AsyncClient, auth_headers: dict[str, str]):
    item = await create_item(async_client, auth_headers, "Single Fetch")
    res = await async_client.get(f"/api/v1/closet/{item['id']}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Single Fetch"


@pytest.mark.asyncio
async def test_cannot_patch_other_users_item(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "patchusera")
    headers_b = await headers_for(async_client, "patchuserb")
    item = await create_item(async_client, headers_a)

    response = await async_client.patch(
        f"/api/v1/closet/{item['id']}",
        headers=headers_b,
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_analyze_preview_does_not_create_closet_row(
    async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
):
    """Preview stages Redis session + response only; no ``closet_items`` row."""
    from io import BytesIO

    from PIL import Image

    from app.api.v1.wardrobe.schemas.closet import VisionAnalysisItem, VisionAnalyzeResponse
    from app.api.v1.wardrobe.services import closet_preview_service

    async def fake_run(_image_bytes: bytes, _content_type: str, scan_id: str, **_kw) -> VisionAnalyzeResponse:
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=1,
            items=[
                VisionAnalysisItem(
                    item_id="det-1",
                    category="tops",
                    name="Fixture Tee",
                    primary_color="navy",
                    confidence_score=0.95,
                )
            ],
            processing_time_ms=1,
            cached=False,
        )

    async def fake_persist_upload(*_args, **_kwargs) -> str:
        return "/uploads/preview_fixture.jpg"

    monkeypatch.setattr(closet_preview_service, "run_pipeline", fake_run)
    monkeypatch.setattr(closet_preview_service, "persist_upload", fake_persist_upload)

    list_before = await async_client.get("/api/v1/closet/", headers=auth_headers)
    assert list_before.json()["total"] == 0

    jpeg_buf = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 50, 60)).save(jpeg_buf, format="JPEG")
    files = {"file": ("preview.jpg", jpeg_buf.getvalue(), "image/jpeg")}
    resp = await async_client.post("/api/v1/closet/analyze-preview", files=files, headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("preview_session_id")
    assert data.get("items")

    list_after = await async_client.get("/api/v1/closet/", headers=auth_headers)
    assert list_after.json()["total"] == 0


@pytest.mark.asyncio
async def test_confirm_preview_persists_closet_items(
    async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
):
    from io import BytesIO

    from PIL import Image

    from app.api.v1.wardrobe.schemas.closet import VisionAnalysisItem, VisionAnalyzeResponse
    from app.api.v1.wardrobe.services import closet_preview_service

    async def fake_run(_image_bytes: bytes, _content_type: str, scan_id: str, **_kw) -> VisionAnalyzeResponse:
        return VisionAnalyzeResponse(
            scan_id=scan_id,
            total_items_detected=1,
            items=[
                VisionAnalysisItem(
                    item_id="det-confirm-1",
                    category="tops",
                    name="Confirm Tee",
                    primary_color="white",
                    confidence_score=0.9,
                )
            ],
            processing_time_ms=1,
            cached=False,
        )

    async def fake_persist_upload(*_args, **_kwargs) -> str:
        return "/uploads/confirm_fixture.jpg"

    monkeypatch.setattr(closet_preview_service, "run_pipeline", fake_run)
    monkeypatch.setattr(closet_preview_service, "persist_upload", fake_persist_upload)

    jpeg_buf = BytesIO()
    Image.new("RGB", (8, 8), color=(200, 200, 200)).save(jpeg_buf, format="JPEG")
    files = {"file": ("confirm.jpg", jpeg_buf.getvalue(), "image/jpeg")}
    prev = await async_client.post("/api/v1/closet/analyze-preview", files=files, headers=auth_headers)
    assert prev.status_code == 200
    session_id = prev.json()["preview_session_id"]

    conf = await async_client.post(
        "/api/v1/closet/confirm",
        headers=auth_headers,
        json={
            "preview_session_id": session_id,
            "items": [
                {
                    "slot_index": 0,
                    "selected": True,
                    "name": "Confirm Tee",
                    "category": "tops",
                    "color": "white",
                }
            ],
        },
    )
    assert conf.status_code == 201
    assert conf.json()["total_saved"] == 1

    listing = await async_client.get("/api/v1/closet/", headers=auth_headers)
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["name"] == "Confirm Tee"


@pytest.mark.asyncio
async def test_cannot_delete_other_users_item(async_client: AsyncClient):
    headers_a = await headers_for(async_client, "deleteusera")
    headers_b = await headers_for(async_client, "deleteuserb")
    item = await create_item(async_client, headers_a)

    response = await async_client.delete(f"/api/v1/closet/{item['id']}", headers=headers_b)

    assert response.status_code == 404
