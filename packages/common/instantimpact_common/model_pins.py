"""Pinned still-pipeline weights. Bootstrap and health share this catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPin:
    id: str
    role: str
    hf_repo: str
    hf_path: str
    dest_kind: str
    filename: str
    profiles: tuple[str, ...]
    approx_gb: float
    sha256: str | None
    gated: bool
    license: str


# dest_kind values match Comfy models/ subfolders (clip also searches text_encoders).
PINS: tuple[ModelPin, ...] = (
    ModelPin(
        id="flux1-dev-fp8",
        role="Packed Flux.1-dev FP8 checkpoint (MVP / rollback)",
        hf_repo="Comfy-Org/flux1-dev",
        hf_path="flux1-dev-fp8.safetensors",
        dest_kind="checkpoints",
        filename="flux1-dev-fp8.safetensors",
        profiles=("fp8",),
        approx_gb=17.0,
        sha256=None,
        gated=False,
        license="FLUX.1 [dev] Non-Commercial License",
    ),
    ModelPin(
        id="flux1-dev-bf16",
        role="Bare bf16 Flux.1-dev UNET (split loader)",
        hf_repo="black-forest-labs/FLUX.1-dev",
        hf_path="flux1-dev.safetensors",
        dest_kind="diffusion_models",
        filename="flux1-dev.safetensors",
        profiles=("bf16",),
        approx_gb=23.8,
        sha256=None,
        gated=True,
        license="FLUX.1 [dev] Non-Commercial License",
    ),
    ModelPin(
        id="flux1-krea-dev",
        role="FLUX.1 Krea [dev] photoreal UNET (split loader, recommended)",
        hf_repo="black-forest-labs/FLUX.1-Krea-dev",
        hf_path="flux1-krea-dev.safetensors",
        dest_kind="diffusion_models",
        filename="flux1-krea-dev.safetensors",
        profiles=("krea",),
        approx_gb=23.8,
        sha256=None,
        gated=True,
        license="FLUX.1 [dev] Non-Commercial License",
    ),
    ModelPin(
        id="flux1-krea-dev-fp8",
        role="Krea photoreal UNET fp8-scaled (VRAM fallback)",
        hf_repo="Comfy-Org/FLUX.1-Krea-dev_ComfyUI",
        hf_path="split_files/diffusion_models/flux1-krea-dev_fp8_scaled.safetensors",
        dest_kind="diffusion_models",
        filename="flux1-krea-dev_fp8_scaled.safetensors",
        profiles=("krea-fp8",),
        approx_gb=11.9,
        sha256="b17a8c21703c4d6ffb0e300dd920eff3cfd35c9a72a1abaf107e3788e408b8d8",
        gated=False,
        license="FLUX.1 [dev] Non-Commercial License",
    ),
    ModelPin(
        id="clip-l",
        role="CLIP-L text encoder",
        hf_repo="comfyanonymous/flux_text_encoders",
        hf_path="clip_l.safetensors",
        dest_kind="clip",
        filename="clip_l.safetensors",
        profiles=("bf16", "krea", "krea-fp8"),
        approx_gb=0.25,
        sha256=None,
        gated=False,
        license="CLIP / see source",
    ),
    ModelPin(
        id="t5xxl-fp16",
        role="T5-XXL fp16 text encoder",
        hf_repo="comfyanonymous/flux_text_encoders",
        hf_path="t5xxl_fp16.safetensors",
        dest_kind="clip",
        filename="t5xxl_fp16.safetensors",
        profiles=("bf16", "krea", "krea-fp8"),
        approx_gb=9.8,
        sha256=None,
        gated=False,
        license="Apache-2.0 (T5)",
    ),
    ModelPin(
        id="ae",
        role="Flux autoencoder",
        hf_repo="black-forest-labs/FLUX.1-dev",
        hf_path="ae.safetensors",
        dest_kind="vae",
        filename="ae.safetensors",
        profiles=("bf16", "krea", "krea-fp8"),
        approx_gb=0.34,
        sha256=None,
        gated=True,
        license="FLUX.1 [dev] Non-Commercial License",
    ),
    ModelPin(
        id="qwen-image-edit-fp8",
        role="Qwen Image Edit FP8 garment editor",
        hf_repo="Comfy-Org/Qwen-Image-Edit_ComfyUI",
        hf_path="split_files/diffusion_models/qwen_image_edit_fp8_e4m3fn.safetensors",
        dest_kind="diffusion_models",
        filename="qwen_image_edit_fp8_e4m3fn.safetensors",
        profiles=("garment",),
        approx_gb=19.03,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="qwen-vl-fp8",
        role="Qwen 2.5 VL text/vision encoder",
        hf_repo="Comfy-Org/Qwen-Image_ComfyUI",
        hf_path="split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
        dest_kind="clip",
        filename="qwen_2.5_vl_7b_fp8_scaled.safetensors",
        profiles=("garment",),
        approx_gb=8.74,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="qwen-image-vae",
        role="Qwen Image VAE",
        hf_repo="Comfy-Org/Qwen-Image_ComfyUI",
        hf_path="split_files/vae/qwen_image_vae.safetensors",
        dest_kind="vae",
        filename="qwen_image_vae.safetensors",
        profiles=("garment",),
        approx_gb=0.24,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="qwen-edit-lightning",
        role="Qwen Image Edit four-step acceleration LoRA",
        hf_repo="lightx2v/Qwen-Image-Lightning",
        hf_path="Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors",
        dest_kind="loras",
        filename="Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors",
        profiles=("garment",),
        approx_gb=0.81,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="wan22-ti2v-5b",
        role="Wan 2.2 TI2V-5B diffusion model",
        hf_repo="Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
        hf_path="split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
        dest_kind="diffusion_models",
        filename="wan2.2_ti2v_5B_fp16.safetensors",
        profiles=("video",),
        approx_gb=10.6,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="wan-umt5-fp8",
        role="Wan UMT5 XXL FP8 text encoder",
        hf_repo="Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        hf_path="split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        dest_kind="clip",
        filename="umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        profiles=("video",),
        approx_gb=6.7,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
    ModelPin(
        id="wan22-vae",
        role="Wan 2.2 video VAE",
        hf_repo="Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
        hf_path="split_files/vae/wan2.2_vae.safetensors",
        dest_kind="vae",
        filename="wan2.2_vae.safetensors",
        profiles=("video",),
        approx_gb=1.4,
        sha256=None,
        gated=False,
        license="Apache-2.0 / see model card",
    ),
)

PROFILES: dict[str, str] = {
    "fp8": "Packed Flux.1-dev FP8 via CheckpointLoaderSimple (MVP / rollback)",
    "bf16": "Split bf16 Flux.1-dev (precision upgrade, still filtered anatomy)",
    "krea": "Split FLUX.1-Krea-dev photoreal UNET + shared encoders (recommended on L40S)",
    "krea-fp8": "Krea photoreal UNET in fp8-scaled form (lower VRAM)",
    "garment": "Local Qwen Image Edit FP8 garment-reference workflow",
    "video": "Wan 2.2 TI2V-5B vertical image-to-video workflow",
}

PROFILE_ENV: dict[str, dict[str, str]] = {
    "fp8": {
        "INSTANTIMPACT_COMFY_LOADER": "checkpoint",
        "INSTANTIMPACT_COMFY_CKPT_NAME": "flux1-dev-fp8.safetensors",
        "INSTANTIMPACT_TRAIN_BASE_MODEL": "black-forest-labs/FLUX.1-dev",
    },
    "bf16": {
        "INSTANTIMPACT_COMFY_LOADER": "split",
        "INSTANTIMPACT_COMFY_UNET_NAME": "flux1-dev.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME1": "clip_l.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME2": "t5xxl_fp16.safetensors",
        "INSTANTIMPACT_COMFY_VAE_NAME": "ae.safetensors",
        "INSTANTIMPACT_TRAIN_BASE_MODEL": "black-forest-labs/FLUX.1-dev",
    },
    "krea": {
        "INSTANTIMPACT_COMFY_LOADER": "split",
        "INSTANTIMPACT_COMFY_UNET_NAME": "flux1-krea-dev.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME1": "clip_l.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME2": "t5xxl_fp16.safetensors",
        "INSTANTIMPACT_COMFY_VAE_NAME": "ae.safetensors",
        "INSTANTIMPACT_TRAIN_BASE_MODEL": "black-forest-labs/FLUX.1-Krea-dev",
    },
    "krea-fp8": {
        "INSTANTIMPACT_COMFY_LOADER": "split",
        "INSTANTIMPACT_COMFY_UNET_NAME": "flux1-krea-dev_fp8_scaled.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME1": "clip_l.safetensors",
        "INSTANTIMPACT_COMFY_CLIP_NAME2": "t5xxl_fp16.safetensors",
        "INSTANTIMPACT_COMFY_VAE_NAME": "ae.safetensors",
        "INSTANTIMPACT_TRAIN_BASE_MODEL": "black-forest-labs/FLUX.1-Krea-dev",
    },
    "garment": {
        "INSTANTIMPACT_QWEN_EDIT_UNET": "qwen_image_edit_fp8_e4m3fn.safetensors",
        "INSTANTIMPACT_QWEN_EDIT_CLIP": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "INSTANTIMPACT_QWEN_EDIT_VAE": "qwen_image_vae.safetensors",
        "INSTANTIMPACT_QWEN_EDIT_LORA": (
            "Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors"
        ),
    },
    "video": {
        "INSTANTIMPACT_ENABLE_VIDEO": "true",
        "INSTANTIMPACT_WAN_UNET": "wan2.2_ti2v_5B_fp16.safetensors",
        "INSTANTIMPACT_WAN_CLIP": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "INSTANTIMPACT_WAN_VAE": "wan2.2_vae.safetensors",
        "INSTANTIMPACT_VIDEO_TIMEOUT": "3600",
    },
}


def pins_for_profile(profile: str) -> tuple[ModelPin, ...]:
    key = profile.strip().lower()
    if key not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown profile {profile!r}. Expected one of: {known}")
    return tuple(p for p in PINS if key in p.profiles)


def pin_by_id(pin_id: str) -> ModelPin:
    for pin in PINS:
        if pin.id == pin_id:
            return pin
    raise ValueError(f"Unknown pin id {pin_id!r}")
