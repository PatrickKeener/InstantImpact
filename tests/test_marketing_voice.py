"""Marketing voice + ad copy API."""

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


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(20, 140, 80)).save(buf, "PNG")
    return buf.getvalue()


def test_marketing_voice_and_ad_copy(client: TestClient):
    created = client.post(
        "/api/characters",
        json={
            "display_name": "Voice Muse",
            "synthetic_confirmed": True,
            "not_real_person_attested": True,
            "attestation_text": "synthetic adult persona for voice tests",
            "personality": {"traits": ["warm"], "tone": "playful"},
            "speaking_style": {"formality": "warm", "emoji_use": "light"},
            "marketing_voice": {
                "tagline": "Soft power, loud results.",
                "audience": "beauty buyers",
                "cta_style": "soft",
                "value_props": ["clean glow"],
                "sample_ads": ["This is my everyday soft reset."],
                "hashtag_style": "light",
            },
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    cid = body["id"]
    assert body["current_version"]["marketing_voice"]["tagline"] == "Soft power, loud results."

    product = client.post(
        "/api/products",
        data={"name": "Glow Mist", "brand": "Muse"},
        files={"image": ("mist.png", _png_bytes(), "image/png")},
    )
    assert product.status_code == 200, product.text
    pid = product.json()["id"]

    copy = client.post(
        f"/api/characters/{cid}/ad-copy",
        json={"product_id": pid, "theme": "glamour", "count": 2, "seed": 3},
    )
    assert copy.status_code == 200, copy.text
    payload = copy.json()
    assert payload["primary"]
    assert len(payload["variants"]) == 2
    assert payload["product_name"] == "Glow Mist"

    assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
    batch = client.post(
        f"/api/characters/{cid}/still-batch",
        json={
            "items": [
                {
                    "type": "still",
                    "count": 1,
                    "theme": "glamour",
                    "product_id": pid,
                    "product_placement": "holding",
                }
            ]
        },
    )
    assert batch.status_code == 200, batch.text
    assets = client.get(f"/api/characters/{cid}/assets").json()
    assert assets
    aid = assets[0]["id"]

    saved = client.post(
        f"/api/characters/{cid}/assets/{aid}/caption",
        json={"caption": payload["primary"], "short": payload["short"], "product_id": pid},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["caption"] == payload["primary"]
    assets2 = client.get(f"/api/characters/{cid}/assets").json()
    meta = next(a for a in assets2 if a["id"] == aid)["meta"]
    assert meta.get("marketing_caption") == payload["primary"]
