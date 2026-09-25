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
)

PROFILES: dict[str, str] = {
    "fp8": "Packed Flux.1-dev FP8 via CheckpointLoaderSimple (MVP / rollback)",
    "bf16": "Split bf16 Flux.1-dev (precision upgrade, still filtered anatomy)",
    "krea": "Split FLUX.1-Krea-dev photoreal UNET + shared encoders (recommended on L40S)",
    "krea-fp8": "Krea photoreal UNET in fp8-scaled form (lower VRAM)",
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
