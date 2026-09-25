from pathlib import Path

from instantimpact_common.flux_inventory import (
    FluxRuntime,
    fail_closed_message,
    find_model,
    inspect_flux_still,
    stills_require_pipeline,
)
from instantimpact_common.model_pins import PROFILE_ENV, pins_for_profile


def _touch(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_pins_for_krea_include_encoders_and_unet():
    names = {p.filename for p in pins_for_profile("krea")}
    assert "flux1-krea-dev.safetensors" in names
    assert "clip_l.safetensors" in names
    assert "t5xxl_fp16.safetensors" in names
    assert "ae.safetensors" in names
    assert PROFILE_ENV["krea"]["INSTANTIMPACT_COMFY_LOADER"] == "split"
    assert "Krea" in PROFILE_ENV["krea"]["INSTANTIMPACT_TRAIN_BASE_MODEL"]


def test_inspect_mock_skips_disk():
    report = inspect_flux_still(
        FluxRuntime(
            mock=True,
            comfy_enabled=False,
            loader="checkpoint",
            comfy_root=None,
            ckpt_name="missing.safetensors",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        )
    )
    assert report["status"] == "mock"
    assert fail_closed_message(report) is None


def test_split_ok_when_all_files_present(tmp_path: Path):
    _touch(tmp_path, "models/diffusion_models/flux1-krea-dev.safetensors")
    _touch(tmp_path, "models/clip/clip_l.safetensors")
    _touch(tmp_path, "models/text_encoders/t5xxl_fp16.safetensors")
    _touch(tmp_path, "models/vae/ae.safetensors")
    report = inspect_flux_still(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="split",
            comfy_root=tmp_path,
            ckpt_name="unused.safetensors",
            unet_name="flux1-krea-dev.safetensors",
            clip_name1="clip_l.safetensors",
            clip_name2="t5xxl_fp16.safetensors",
            vae_name="ae.safetensors",
        ),
        comfy_reachable=True,
    )
    assert report["status"] == "ok"
    assert report["missing_weights"] == []
    assert fail_closed_message(report) is None


def test_split_missing_unet_is_missing_weights(tmp_path: Path):
    _touch(tmp_path, "models/clip/clip_l.safetensors")
    _touch(tmp_path, "models/clip/t5xxl_fp16.safetensors")
    _touch(tmp_path, "models/vae/ae.safetensors")
    report = inspect_flux_still(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="split",
            comfy_root=tmp_path,
            ckpt_name="unused.safetensors",
            unet_name="flux1-krea-dev.safetensors",
            clip_name1="clip_l.safetensors",
            clip_name2="t5xxl_fp16.safetensors",
            vae_name="ae.safetensors",
        ),
        comfy_reachable=True,
    )
    assert report["status"] == "missing_weights"
    assert "flux1-krea-dev.safetensors" in report["missing_weights"]
    msg = fail_closed_message(report)
    assert msg is not None
    assert "bootstrap_models.py" in msg
    assert "--profile krea" in msg
    assert str(tmp_path) in msg


def test_find_model_searches_text_encoders(tmp_path: Path):
    path = _touch(tmp_path, "models/text_encoders/clip_l.safetensors")
    assert find_model(tmp_path, "clip", "clip_l.safetensors") == path


def test_find_model_walks_models_tree(tmp_path: Path):
    path = _touch(tmp_path, "models/vae/flux/ae.safetensors")
    assert find_model(tmp_path, "vae", "ae.safetensors") == path


def test_missing_nodes_from_object_info(tmp_path: Path):
    _touch(tmp_path, "models/checkpoints/flux1-dev-fp8.safetensors")
    report = inspect_flux_still(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="checkpoint",
            comfy_root=tmp_path,
            ckpt_name="flux1-dev-fp8.safetensors",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        object_info={"KSampler": {}},
        comfy_reachable=True,
    )
    assert report["status"] == "missing_nodes"
    assert "CLIPTextEncodeFlux" in report["missing_nodes"]


def test_comfy_down_with_weights_present_is_idle(tmp_path: Path):
    _touch(tmp_path, "models/checkpoints/flux1-dev-fp8.safetensors")
    report = inspect_flux_still(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="checkpoint",
            comfy_root=tmp_path,
            ckpt_name="flux1-dev-fp8.safetensors",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        comfy_reachable=False,
    )
    assert report["status"] == "idle"
    assert fail_closed_message(report) is None


def test_unverified_root_does_not_fail_closed():
    report = inspect_flux_still(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="checkpoint",
            comfy_root=None,
            ckpt_name="flux1-dev-fp8.safetensors",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        comfy_reachable=True,
    )
    assert report["status"] == "ok"
    assert report["unverified"] is True
    assert fail_closed_message(report) is None


def test_bootstrap_dry_run_lists_krea_destinations(tmp_path: Path, capsys):
    import importlib.util

    (tmp_path / "models").mkdir()
    script = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_models.py"
    spec = importlib.util.spec_from_file_location("bootstrap_models", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rc = mod.main(["--profile", "krea", "--dry-run", "--comfy-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "flux1-krea-dev.safetensors" in out
    assert "INSTANTIMPACT_COMFY_LOADER=split" in out


def test_stills_require_pipeline_skips_train():
    assert stills_require_pipeline("seed_gallery")
    assert stills_require_pipeline("still_batch")
    assert not stills_require_pipeline("lora_train")
