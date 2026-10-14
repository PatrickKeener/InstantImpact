"""Character LoRA install, preflight, and train registration."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from instantimpact_common.lora_comfy import (
    character_lora_problem,
    comfy_lora_filename,
    ensure_character_lora,
    install_character_lora,
)


def test_install_publishes_the_final_file_atomically(tmp_path: Path):
    src = tmp_path / "model.safetensors"
    src.write_bytes(b"weights")
    folder = tmp_path / "loras"
    name = comfy_lora_filename("ruby-2", 1)

    installed = install_character_lora(src, folder, name)

    assert installed.name == "ii_ruby-2_v001.safetensors"
    assert installed.read_bytes() == b"weights"
    assert list(folder.glob(".*.partial")) == []
    assert character_lora_problem(name, folder) is None


def test_ensure_copies_saved_weights_when_comfy_copy_is_missing(tmp_path: Path):
    src = tmp_path / "data" / "model.safetensors"
    src.parent.mkdir()
    src.write_bytes(b"trained")
    loras = tmp_path / "loras"
    name = "ii_ruby-2_v001.safetensors"

    assert ensure_character_lora(name, src, loras) is None
    assert (loras / name).read_bytes() == b"trained"


def test_missing_lora_without_saved_weights_is_one_error(tmp_path: Path):
    message = ensure_character_lora("ii_ruby-2_v001.safetensors", None, tmp_path)
    assert message is not None
    assert "ii_ruby-2_v001.safetensors" in message
    assert "not installed" in message


def test_install_refuses_to_leave_a_partial_file(tmp_path: Path):
    src = tmp_path / "model.safetensors"
    src.write_bytes(b"weights")
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError):
        install_character_lora(src, blocked, "ii_ruby-2_v001.safetensors")
    assert not (tmp_path / "ii_ruby-2_v001.safetensors").exists()


def _real_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path, Path]:
    data = tmp_path / "data"
    (data / "db").mkdir(parents=True)
    comfy = tmp_path / "ComfyUI"
    for rel in (
        "models/diffusion_models/flux1-krea-dev.safetensors",
        "models/clip/clip_l.safetensors",
        "models/clip/t5xxl_fp16.safetensors",
        "models/vae/ae.safetensors",
    ):
        path = comfy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"w")
    loras = comfy / "models" / "loras"
    loras.mkdir()
    db = data / "db" / "ii.sqlite"
    monkeypatch.setenv("INSTANTIMPACT_DATA_DIR", str(data))
    monkeypatch.setenv("INSTANTIMPACT_DATABASE_URL", f"sqlite+aiosqlite:///{db.as_posix()}")
    monkeypatch.setenv("INSTANTIMPACT_MOCK_GENERATION", "false")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_ENABLED", "true")
    monkeypatch.setenv("INSTANTIMPACT_COMFY_DIR", str(comfy))
    monkeypatch.setenv("INSTANTIMPACT_COMFY_LORAS_DIR", str(loras))
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

    return TestClient(create_app()), data, loras


@pytest.mark.asyncio
async def test_seed_gallery_installs_saved_lora_before_queueing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, data, loras = _real_client(tmp_path, monkeypatch)
    with client:
        created = client.post(
            "/api/characters",
            json={
                "display_name": "Ruby 2",
                "synthetic_confirmed": True,
                "not_real_person_attested": True,
                "attestation_text": "synthetic adult persona for tests",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        cid = body["id"]
        assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
        weights = data / "characters" / cid / "versions" / "v001" / "lora" / "model.safetensors"
        weights.parent.mkdir(parents=True, exist_ok=True)
        weights.write_bytes(b"trained-lora")
        registered = client.post(
            f"/api/characters/{cid}/lora/register",
            json={"source_path": str(weights), "install_to_comfy": True},
        )
        assert registered.status_code == 200, registered.text
        installed = loras / "ii_ruby-2_v001.safetensors"
        assert installed.is_file()
        installed.unlink()
        from app.db.models import Character
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            row = await db.get(Character, cid)
            assert row is not None
            row.status = "bootstrap"
            await db.commit()

        seed = client.post(
            f"/api/characters/{cid}/seed-gallery",
            json={"count": 2, "themes": ["portrait"]},
        )
        assert seed.status_code == 200, seed.text
        assert installed.read_bytes() == b"trained-lora"


def test_seed_gallery_fails_once_when_lora_cannot_be_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _data, _loras = _real_client(tmp_path, monkeypatch)
    with client:
        created = client.post(
            "/api/characters",
            json={
                "display_name": "Ruby 2",
                "synthetic_confirmed": True,
                "not_real_person_attested": True,
                "attestation_text": "synthetic adult persona for tests",
            },
        )
        cid = created.json()["id"]
        assert client.post(f"/api/characters/{cid}/bootstrap").status_code == 200
        patched = client.patch(
            f"/api/characters/{cid}",
            json={"pipeline_params": {"flux": {"comfy_lora_name": "ii_ruby-2_v001.safetensors"}}},
        )
        assert patched.status_code == 200, patched.text
        seed = client.post(
            f"/api/characters/{cid}/seed-gallery",
            json={"count": 3, "themes": ["portrait"]},
        )
        assert seed.status_code == 503, seed.text
        assert seed.json()["detail"].count("ii_ruby-2_v001.safetensors") == 1


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

    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None


@pytest.mark.asyncio
async def test_failed_lora_registration_marks_the_train_job_failed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    created = client.post(
        "/api/characters",
        json={
            "display_name": "Ruby 2",
            "synthetic_confirmed": True,
            "not_real_person_attested": True,
            "attestation_text": "synthetic adult persona for tests",
        },
    )
    assert created.status_code == 200, created.text

    from app.db.models import Job
    from app.db.session import get_session_factory
    from app.services.jobs import apply_job_event, get_job
    from instantimpact_common.enums import JobStatus, JobType

    factory = get_session_factory()
    job_id = "8d61444b-0000-4000-8000-000000000001"
    async with factory() as db:
        db.add(
            Job(
                id=job_id,
                type=JobType.LORA_TRAIN,
                status=JobStatus.RUNNING,
                character_id=created.json()["id"],
                request_json={},
            )
        )
        await db.commit()

    async def _fail(*_args, **_kwargs):
        raise RuntimeError("Comfy LoRA directory is read-only")

    monkeypatch.setattr("app.services.lora.register_lora", _fail)
    async with factory() as db:
        await apply_job_event(
            db,
            {
                "job_id": job_id,
                "event": "completed",
                "lora_path": "/tmp/model.safetensors",
            },
        )
        job = await get_job(db, job_id)
        assert job.status == JobStatus.FAILED
        assert job.error_code == "lora_register_failed"
        assert "read-only" in (job.error_message or "")
