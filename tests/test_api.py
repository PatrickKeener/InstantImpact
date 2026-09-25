"""API flow tests (mock generation, no Redis/Comfy required)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


def _create_attested(client: TestClient, name: str = "Aria Test") -> dict:
    r = client.post(
        "/api/characters",
        json={
            "display_name": name,
            "synthetic_confirmed": True,
            "not_real_person_attested": True,
            "attestation_text": "synthetic adult persona for tests",
            "appearance": {"hair_color": "auburn", "eye_color": "green"},
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client: TestClient):
    r = client.get("/api/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "instantimpact"
    assert "redis_ok" in body
    assert body["mvp"]["mock_generation"] is True
    assert body["pipelines"]["flux_still"] == "mock"


def test_seed_gallery_fails_closed_when_split_weights_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    (data / "db").mkdir(parents=True)
    comfy = tmp_path / "ComfyUI"
    (comfy / "models").mkdir(parents=True)
    db = data / "db" / "ii.sqlite"
    monkeypatch.setenv("INSTANTIMPACT_DATA_DIR", str(data))
    monkeypatch.setenv("INSTANTIMPACT_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("INSTANTIMPACT_MOCK_GENERATION", "false")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_ENABLED", "true")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_DIR", str(comfy))
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LOADER", "split")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_UNET_NAME", "flux1-krea-dev.safetensors")
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
        created = c.post(
            "/api/characters",
            json={
                "display_name": "Krea Gate",
                "synthetic_confirmed": True,
                "not_real_person_attested": True,
                "attestation_text": "synthetic adult persona for tests",
            },
        )
        assert created.status_code == 200, created.text
        cid = created.json()["id"]
        assert c.post(f"/api/characters/{cid}/bootstrap").status_code == 200
        seed = c.post(f"/api/characters/{cid}/seed-gallery", json={"count": 1, "themes": ["portrait"]})
        assert seed.status_code == 503, seed.text
        assert "flux1-krea-dev.safetensors" in seed.json()["detail"]
        assert "bootstrap_models.py" in seed.json()["detail"]

    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None


def test_media_404(client: TestClient):
    r = client.get("/api/system/media/does/not/exist.png")
    assert r.status_code == 404


def test_media_rejects_traversal(client: TestClient):
    r = client.get("/api/system/media/../pyproject.toml")
    assert r.status_code in (400, 404)


def _lock_ready(client: TestClient, cid: str) -> str:
    """Bootstrap + lock without a LoRA so tests can exercise the ready path."""
    assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
    version_id = client.get(f"/api/characters/{cid}").json()["current_version"]["id"]
    r = client.post(
        f"/api/characters/{cid}/lock",
        json={
            "version_id": version_id,
            "checklist_attestation": "I confirm adult synthetic lock for tests.",
            "confirm_adult": True,
            "confirm_synthetic": True,
            "confirm_not_real_person": True,
            "allow_without_lora": True,
        },
    )
    assert r.status_code == 200, r.text
    return version_id


def test_quality_knobs_do_not_fork_a_locked_version(client: TestClient):
    cid = _create_attested(client, "Locked Knobs")["id"]
    locked_version_id = _lock_ready(client, cid)

    r = client.patch(
        f"/api/characters/{cid}",
        json={"pipeline_params": {"flux": {"cfg": 3.5, "detail_lora_name": "skin.safetensors"}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["retrain_version_id"] is None

    version = body["current_version"]
    assert version["id"] == locked_version_id
    assert version["pipeline_params"]["flux"]["cfg"] == 3.5
    assert version["pipeline_params"]["flux"]["detail_lora_name"] == "skin.safetensors"
    # Untouched knobs survive the merge
    assert version["pipeline_params"]["flux"]["lora_strength"] == 0.85


def test_profile_edit_still_forks_a_locked_version(client: TestClient):
    cid = _create_attested(client, "Locked Profile")["id"]
    locked_version_id = _lock_ready(client, cid)

    r = client.patch(f"/api/characters/{cid}", json={"appearance": {"hair_color": "black"}})
    assert r.status_code == 200, r.text
    body = r.json()
    # Identity edits still open a retrain track; the locked version keeps serving generation.
    assert body["retrain_version_id"] is not None
    assert body["retrain_version_id"] != locked_version_id
    assert body["locked_version_id"] == locked_version_id


def test_character_ref_pack_path_is_portable(client: TestClient):
    character = _create_attested(client, "Portable Refs")
    ref_path = character["current_version"]["ref_pack_path"]
    assert ref_path.startswith("characters/")
    assert "\\" not in ref_path
    assert ":" not in ref_path


def test_seed_gallery_requires_attest(client: TestClient):
    r = client.post("/api/characters", json={"display_name": "No Attest"})
    assert r.status_code == 200
    cid = r.json()["id"]
    g = client.post(f"/api/characters/{cid}/seed-gallery", json={"count": 2})
    assert g.status_code == 400


def test_character_still_approve_dataset_lock(client: TestClient):
    c = _create_attested(client)
    cid = c["id"]
    b = client.post(f"/api/characters/{cid}/bootstrap")
    assert b.status_code == 200, b.text

    seed = client.post(
        f"/api/characters/{cid}/seed-gallery",
        json={"count": 4, "themes": ["portrait"]},
    )
    assert seed.status_code == 200, seed.text
    job = seed.json()
    # Background mock should have completed by the time TestClient returns
    job2 = client.get(f"/api/jobs/{job['id']}").json()
    assert job2["status"] in ("completed", "queued", "running")
    if job2["status"] != "completed":
        # Poll a few times in case background task is slightly delayed
        import time

        for _ in range(30):
            time.sleep(0.05)
            job2 = client.get(f"/api/jobs/{job['id']}").json()
            if job2["status"] == "completed":
                break
    assert job2["status"] == "completed", job2

    assets = client.get(f"/api/characters/{cid}/assets").json()
    assert len(assets) >= 4
    for a in assets[:4]:
        d = client.post(f"/api/assets/{a['id']}/decision", json={"decision": "approved"})
        assert d.status_code == 200

    ds = client.post(f"/api/characters/{cid}/dataset/build", json={"decision": "approved", "min_images": 4})
    assert ds.status_code == 200, ds.text
    assert ds.json()["image_count"] >= 4

    version_id = client.get(f"/api/characters/{cid}").json()["current_version"]["id"]
    lock_fail = client.post(
        f"/api/characters/{cid}/lock",
        json={
            "version_id": version_id,
            "checklist_attestation": "I confirm adult synthetic lock for tests.",
            "confirm_adult": True,
            "confirm_synthetic": True,
            "confirm_not_real_person": True,
            "allow_without_lora": False,
        },
    )
    assert lock_fail.status_code == 400

    lock_ok = client.post(
        f"/api/characters/{cid}/lock",
        json={
            "version_id": version_id,
            "checklist_attestation": "I confirm adult synthetic lock for tests.",
            "confirm_adult": True,
            "confirm_synthetic": True,
            "confirm_not_real_person": True,
            "allow_without_lora": True,
        },
    )
    assert lock_ok.status_code == 200, lock_ok.text
    assert lock_ok.json()["character"]["status"] == "ready"

    still = client.post(
        f"/api/characters/{cid}/still-batch",
        json={
            "title": "test batch",
            "items": [{"type": "still", "count": 1, "theme": "portrait"}],
        },
    )
    assert still.status_code == 200, still.text

    approved = [a for a in client.get(f"/api/characters/{cid}/assets").json() if a["decision"] == "approved"]
    aset = client.post(
        f"/api/characters/{cid}/approved-sets",
        json={"title": "Test set", "asset_ids": [approved[0]["id"]]},
    )
    assert aset.status_code == 200, aset.text
    exp = client.post(
        f"/api/approved-sets/{aset.json()['id']}/export",
        json={"confirm_adult_synthetic": True},
    )
    assert exp.status_code == 200, exp.text
    assert exp.json()["export_path"]
