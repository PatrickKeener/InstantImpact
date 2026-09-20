"""Product library + product-aware still batch."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    (data / "db").mkdir(parents=True)
    db = data / "db" / "ii.sqlite"
    monkeypatch.setenv("INSTANTIMPACT_DATA_DIR", str(data))
    monkeypatch.setenv("INSTANTIMPACT_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("INSTANTIMPACT_MOCK_GENERATION", "true")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_ENABLED", "false")
    monkeypatch.setenv("INSTANTIMPACT_REQUIRE_AUTH_TOKEN", "false")
    monkeypatch.setenv("INSTANTIMPACT_API_TOKEN", "")
    monkeypatch.setenv("INSTANTIMPACT_HOST", "127.0.0.1")
    monkeypatch.setenv("INSTANTIMPACT_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("INSTANTIMPACT_CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("INSTANTIMPACT_ENABLE_PRODUCT_UPLOADS", "true")

    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.session as db_session

    db_session._engine = None
    db_session._session_factory = None

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None


def _png_bytes(color=(40, 120, 200), size=(128, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, "PNG")
    return buf.getvalue()


def _create_attested(client: TestClient) -> dict:
    r = client.post(
        "/api/characters",
        json={
            "display_name": "Adria Product",
            "synthetic_confirmed": True,
            "not_real_person_attested": True,
            "attestation_text": "synthetic adult persona for product tests",
            "appearance": {"hair_color": "black", "eye_color": "brown"},
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_product_placements(client: TestClient):
    r = client.get("/api/products/placements")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["placements"]}
    assert "holding" in ids
    assert "featured" in ids


def test_create_list_delete_product(client: TestClient):
    files = {"image": ("serum.png", _png_bytes(), "image/png")}
    data = {
        "name": "Aurora Serum",
        "brand": "Aurora",
        "description": "frosted glass bottle gold dropper",
    }
    created = client.post("/api/products", data=data, files=files)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Aurora Serum"
    assert body["primary_path"].startswith("products/")
    assert body["thumb_path"]

    listed = client.get("/api/products")
    assert listed.status_code == 200
    assert any(p["id"] == body["id"] for p in listed.json())

    media = client.get(f"/api/system/media/{body['primary_path']}")
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/")

    deleted = client.delete(f"/api/products/{body['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_still_batch_with_product_ref(client: TestClient):
    c = _create_attested(client)
    cid = c["id"]
    assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200

    files = {"image": ("bottle.png", _png_bytes((180, 60, 40)), "image/png")}
    product = client.post(
        "/api/products",
        data={"name": "Ruby Elixir", "description": "ruby glass vial"},
        files=files,
    ).json()

    batch = client.post(
        f"/api/characters/{cid}/still-batch",
        json={
            "title": "product ad batch",
            "items": [
                {
                    "type": "still",
                    "count": 2,
                    "theme": "glamour",
                    "outfit_hint": "silk blouse",
                    "product_id": product["id"],
                    "product_placement": "holding",
                }
            ],
        },
    )
    assert batch.status_code == 200, batch.text
    job = batch.json()
    assert job["status"] in ("queued", "running", "completed")

    job2 = client.get(f"/api/jobs/{job['id']}").json()
    assert job2["status"] == "completed", job2
    assert len(job2["items"]) == 2
    req0 = job2["items"][0]["request"]
    assert req0["product_id"] == product["id"]
    assert req0["product_name"] == "Ruby Elixir"
    assert req0["product_ref_path"]
    assert "holding" in (req0.get("product_placement") or "")

    assets = client.get(f"/api/characters/{cid}/assets").json()
    assert len(assets) >= 2
    pos = assets[0].get("prompt_positive") or ""
    assert "Ruby Elixir" in pos or "product" in pos.lower()
