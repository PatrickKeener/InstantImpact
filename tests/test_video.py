"""Video clip length helpers and lookbook enqueue."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from instantimpact_common.video import (
    DEFAULT_VIDEO_MOTION,
    LOOKBOOK_MOTION,
    WAN_FRAMES_DEFAULT,
    duration_seconds,
    motion_for_item,
    snap_wan_frames,
)
from PIL import Image


def test_snap_wan_frames_lands_on_4n_plus_1():
    assert snap_wan_frames(None) == WAN_FRAMES_DEFAULT
    assert snap_wan_frames(80) == 81
    assert snap_wan_frames(81) == 81
    assert snap_wan_frames(120) == 121
    assert snap_wan_frames(160) == 161
    assert snap_wan_frames(200) == 161
    assert snap_wan_frames(10) == 17
    assert duration_seconds(121, 16) == 7.56
    assert duration_seconds(161, 16) == 10.06


def test_lookbook_motion_replaces_generic_camera_push():
    assert motion_for_item(motion=DEFAULT_VIDEO_MOTION) == DEFAULT_VIDEO_MOTION
    assert (
        motion_for_item(
            motion=DEFAULT_VIDEO_MOTION,
            product_kind="garment",
            product_placement="wearing",
        )
        == LOOKBOOK_MOTION
    )
    custom = "slow spin showing the hemline"
    assert (
        motion_for_item(
            motion=custom,
            product_kind="garment",
            product_placement="wearing",
        )
        == custom
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    (data / "db").mkdir(parents=True)
    db = data / "db" / "ii.sqlite"
    monkeypatch.setenv("INSTANTIMPACT_DATA_DIR", str(data))
    monkeypatch.setenv("INSTANTIMPACT_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("INSTANTIMPACT_MOCK_GENERATION", "true")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_ENABLED", "false")
    monkeypatch.setenv("INSTANTIMPACT_ENABLE_VIDEO", "true")
    monkeypatch.setenv("INSTANTIMPACT_ENABLE_PRODUCT_UPLOADS", "true")
    monkeypatch.setenv("INSTANTIMPACT_REQUIRE_AUTH_TOKEN", "false")
    monkeypatch.setenv("INSTANTIMPACT_API_TOKEN", "")
    monkeypatch.setenv("INSTANTIMPACT_HOST", "127.0.0.1")
    monkeypatch.setenv("INSTANTIMPACT_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("INSTANTIMPACT_CORS_ORIGINS", "http://127.0.0.1:5173")

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


def _create_attested(client: TestClient, name: str = "Lookbook") -> dict:
    r = client.post(
        "/api/characters",
        json={
            "display_name": name,
            "synthetic_confirmed": True,
            "not_real_person_attested": True,
            "attestation_text": "synthetic adult persona for video tests",
            "appearance": {"hair_color": "black", "eye_color": "brown"},
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _approved_still(client: TestClient, cid: str) -> str:
    imported = client.post(
        f"/api/characters/{cid}/assets/import",
        files=[("files", ("source.png", _png_bytes(), "image/png"))],
        data={"confirm_synthetic": "true", "auto_approve": "true"},
    )
    assert imported.status_code == 200, imported.text
    return imported.json()["assets"][0]["id"]


def _create_garment(client: TestClient) -> dict:
    created = client.post(
        "/api/products",
        data={
            "name": "Ruby Wrap Dress",
            "product_kind": "garment",
            "garment_category": "wrap dress",
            "garment_color": "ruby red",
            "garment_material": "silk",
        },
        files={"image": ("dress.png", _png_bytes((150, 20, 40)), "image/png")},
    )
    assert created.status_code == 200, created.text
    return created.json()


def test_video_defaults_to_longer_clip(client: TestClient):
    cid = _create_attested(client, "Longer Clip")["id"]
    asset_id = _approved_still(client, cid)
    video = client.post(
        f"/api/characters/{cid}/assets/{asset_id}/video",
        json={"motion_prompt": "gentle turn toward camera"},
    )
    assert video.status_code == 200, video.text
    job = client.get(f"/api/jobs/{video.json()['id']}").json()
    req = job["items"][0]["request"]
    assert req["video_frames"] == 121
    assert req["video_fps"] == 16
    assets = client.get(f"/api/characters/{cid}/assets").json()
    clip = next(a for a in assets if a["kind"] == "video")
    assert clip["meta"]["duration_seconds"] == 7.56
    assert clip["meta"]["frames"] == 121


def test_lookbook_video_dresses_from_garment_product(client: TestClient):
    cid = _create_attested(client)["id"]
    asset_id = _approved_still(client, cid)
    garment = _create_garment(client)
    video = client.post(
        f"/api/characters/{cid}/assets/{asset_id}/video",
        json={
            "motion_prompt": DEFAULT_VIDEO_MOTION,
            "frames": 161,
            "product_id": garment["id"],
        },
    )
    assert video.status_code == 200, video.text
    job = client.get(f"/api/jobs/{video.json()['id']}").json()
    req = job["items"][0]["request"]
    assert req["product_id"] == garment["id"]
    assert req["product_kind"] == "garment"
    assert req["product_placement"] == "wearing"
    assert req["product_ref_path"]
    assert req["video_frames"] == 161
    assert req["video_motion"] == LOOKBOOK_MOTION
    assert req["skip_garment_tryon"] is False
    assets = client.get(f"/api/characters/{cid}/assets").json()
    clip = next(a for a in assets if a["kind"] == "video")
    assert clip["meta"]["product_id"] == garment["id"]
    assert clip["meta"]["product_kind"] == "garment"
    assert clip["meta"]["lookbook"] is True
    assert clip["meta"]["duration_seconds"] == 10.06


def test_video_inherits_garment_from_source_still(client: TestClient):
    cid = _create_attested(client, "Inherit Dress")["id"]
    assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
    garment = _create_garment(client)
    batch = client.post(
        f"/api/characters/{cid}/still-batch",
        json={
            "title": "dress stills",
            "items": [
                {
                    "type": "still",
                    "count": 1,
                    "theme": "glamour",
                    "product_id": garment["id"],
                    "product_placement": "wearing",
                }
            ],
        },
    )
    assert batch.status_code == 200, batch.text
    stills = [a for a in client.get(f"/api/characters/{cid}/assets").json() if a["kind"] == "still"]
    assert stills
    still = stills[0]
    assert still["meta"].get("product_id") == garment["id"]
    decided = client.post(
        f"/api/assets/{still['id']}/decision",
        json={"decision": "approved"},
    )
    assert decided.status_code == 200, decided.text
    video = client.post(
        f"/api/characters/{cid}/assets/{still['id']}/video",
        json={"motion_prompt": DEFAULT_VIDEO_MOTION},
    )
    assert video.status_code == 200, video.text
    req = client.get(f"/api/jobs/{video.json()['id']}").json()["items"][0]["request"]
    assert req["product_id"] == garment["id"]
    assert req["product_kind"] == "garment"
    assert req["product_placement"] == "wearing"
    assert req["skip_garment_tryon"] is True
    assert req["video_motion"] == LOOKBOOK_MOTION


def test_dress_endpoint_creates_dressed_still_then_video_skips_tryon(client: TestClient):
    cid = _create_attested(client, "Dress First")["id"]
    asset_id = _approved_still(client, cid)
    garment = _create_garment(client)
    dressed = client.post(
        f"/api/characters/{cid}/assets/{asset_id}/dress",
        json={"product_id": garment["id"], "product_placement": "wearing"},
    )
    assert dressed.status_code == 200, dressed.text
    job = client.get(f"/api/jobs/{dressed.json()['id']}").json()
    assert job["type"] == "garment_tryon"
    req = job["items"][0]["request"]
    assert req["product_id"] == garment["id"]
    assert req["product_kind"] == "garment"
    assert req["product_placement"] == "wearing"
    assert req["source_asset_id"] == asset_id
    assert req["skip_garment_tryon"] is False
    stills = [a for a in client.get(f"/api/characters/{cid}/assets").json() if a["kind"] == "still"]
    tryon = next(a for a in stills if a["id"] != asset_id)
    assert tryon["meta"].get("product_conditioning") == "qwen_image_edit_tryon"
    assert tryon["meta"].get("product_id") == garment["id"]
    decided = client.post(f"/api/assets/{tryon['id']}/decision", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    video = client.post(
        f"/api/characters/{cid}/assets/{tryon['id']}/video",
        json={"motion_prompt": DEFAULT_VIDEO_MOTION},
    )
    assert video.status_code == 200, video.text
    vreq = client.get(f"/api/jobs/{video.json()['id']}").json()["items"][0]["request"]
    assert vreq["skip_garment_tryon"] is True
    assert vreq["product_id"] == garment["id"]


def test_validation_sheet_enqueues_six_shots(client: TestClient):
    cid = _create_attested(client, "Sheet")["id"]
    assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
    sheet = client.post(f"/api/characters/{cid}/validation-sheet", json={})
    assert sheet.status_code == 200, sheet.text
    job = client.get(f"/api/jobs/{sheet.json()['id']}").json()
    assert job["type"] == "validation_sheet"
    assert len(job["items"]) == 6
    themes = [item["request"]["theme"] for item in job["items"]]
    assert themes == [
        "portrait",
        "portrait",
        "glamour",
        "casual_bedroom",
        "outdoor_day",
        "lingerie_set",
    ]
