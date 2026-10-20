from pathlib import Path

from instantimpact_common.flux_inventory import (
    FluxRuntime,
    discover_detail_lora,
    discover_pulid_model,
    fail_closed_message,
    find_model,
    garment_require_pipeline,
    inspect_flux_still,
    inspect_garment_tryon,
    inspect_wan_video,
    stills_require_pipeline,
    video_require_pipeline,
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


def test_marketing_profiles_pin_all_required_models():
    garment = {p.filename for p in pins_for_profile("garment")}
    assert {
        "qwen_image_edit_fp8_e4m3fn.safetensors",
        "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "qwen_image_vae.safetensors",
        "Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors",
    } <= garment
    video = {p.filename for p in pins_for_profile("video")}
    assert {
        "wan2.2_ti2v_5B_fp16.safetensors",
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "wan2.2_vae.safetensors",
    } <= video
    assert PROFILE_ENV["video"]["INSTANTIMPACT_ENABLE_VIDEO"] == "true"


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


def test_docker_stub_loras_only_is_unverified_not_missing(tmp_path: Path):
    """Bind-mounting only models/loras creates parent dirs without the weights."""
    _touch(tmp_path, "models/loras/.keep")
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
    assert report["missing_weights"] == []
    assert report["unverified"] is True
    assert fail_closed_message(report) is None


def test_split_missing_unet_is_missing_weights(tmp_path: Path):
    (tmp_path / "models" / "diffusion_models").mkdir(parents=True)
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


def test_discover_pulid_model_prefers_flux_weights(tmp_path: Path):
    _touch(tmp_path, "models/pulid/pulid_v1.safetensors")
    _touch(tmp_path, "models/pulid/pulid_flux_v0.9.1.safetensors")
    assert discover_pulid_model(tmp_path) == "pulid_flux_v0.9.1.safetensors"
    assert discover_pulid_model(tmp_path / "missing") is None


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
    assert stills_require_pipeline("validation_sheet")
    assert not stills_require_pipeline("lora_train")
    assert not stills_require_pipeline("garment_tryon")
    assert not stills_require_pipeline("video_i2v")
    assert video_require_pipeline("video_i2v")
    assert garment_require_pipeline("garment_tryon")
    assert garment_require_pipeline("video_i2v", units_need_tryon=True)
    assert not garment_require_pipeline("video_i2v", units_need_tryon=False)


def test_discover_detail_lora_skips_qwen_lightning(tmp_path: Path):
    _touch(tmp_path, "models/loras/Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors")
    _touch(tmp_path, "models/loras/skin_realism_v1.safetensors")
    _touch(tmp_path, "models/loras/flux_anatomy_detail.safetensors")
    assert discover_detail_lora(tmp_path) == "flux_anatomy_detail.safetensors"


def test_inspect_garment_missing_weights(tmp_path: Path):
    (tmp_path / "models" / "diffusion_models").mkdir(parents=True)
    (tmp_path / "models" / "clip").mkdir(parents=True)
    (tmp_path / "models" / "vae").mkdir(parents=True)
    (tmp_path / "models" / "loras").mkdir(parents=True)
    report = inspect_garment_tryon(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="split",
            comfy_root=tmp_path,
            ckpt_name="x",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        comfy_reachable=True,
    )
    assert report["status"] == "missing_weights"
    assert report["pipeline"] == "garment_tryon"
    msg = fail_closed_message(report)
    assert msg is not None
    assert "--profile garment" in msg
    assert "Qwen garment" in msg


def test_inspect_wan_disabled_does_not_fail_closed():
    report = inspect_wan_video(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="split",
            comfy_root=None,
            ckpt_name="x",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        enabled=False,
        comfy_reachable=True,
    )
    assert report["status"] == "disabled"
    assert fail_closed_message(report) is None


def test_inspect_garment_ok_when_files_present(tmp_path: Path):
    _touch(tmp_path, "models/diffusion_models/qwen_image_edit_fp8_e4m3fn.safetensors")
    _touch(tmp_path, "models/clip/qwen_2.5_vl_7b_fp8_scaled.safetensors")
    _touch(tmp_path, "models/vae/qwen_image_vae.safetensors")
    _touch(tmp_path, "models/loras/Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors")
    report = inspect_garment_tryon(
        FluxRuntime(
            mock=False,
            comfy_enabled=True,
            loader="split",
            comfy_root=tmp_path,
            ckpt_name="x",
            unet_name="x",
            clip_name1="a",
            clip_name2="b",
            vae_name="c",
        ),
        comfy_reachable=True,
    )
    assert report["status"] == "ok"
    assert fail_closed_message(report) is None
