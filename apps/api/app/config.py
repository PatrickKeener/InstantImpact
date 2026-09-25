from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path already used for data_dir defaults


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INSTANTIMPACT_",
        extra="ignore",
    )

    # all-in-one (recommended on nemesis) | control | gpu
    node_role: str = "all-in-one"
    node_name: str = "local"

    data_dir: Path = Path("./data")
    host: str = "127.0.0.1"
    port: int = 8000
    public_base_url: str = "http://127.0.0.1:8000"
    # Comma-separated browser origins. LAN hosts belong in .env, not here.
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    database_url: str = "sqlite+aiosqlite:///./data/db/instantimpact.sqlite"

    redis_url: str = "redis://127.0.0.1:6379/0"
    comfy_url: str = "http://127.0.0.1:8188"
    comfy_enabled: bool = False
    comfy_dir: str = ""
    # checkpoint = packed file; split = UNET + CLIP + VAE (bf16 Flux / Krea)
    comfy_loader: str = "checkpoint"
    # Checkpoint filename inside ComfyUI/models/checkpoints/
    comfy_ckpt_name: str = "flux1-dev-fp8.safetensors"
    comfy_unet_name: str = "flux1-dev.safetensors"
    comfy_unet_dtype: str = "default"
    comfy_clip_name1: str = "clip_l.safetensors"
    comfy_clip_name2: str = "t5xxl_fp16.safetensors"
    comfy_vae_name: str = "ae.safetensors"
    comfy_timeout_seconds: float = 600.0
    # Where to install character LoRAs for Comfy (models/loras)
    comfy_loras_dir: str = str(Path.home() / "ComfyUI" / "models" / "loras")
    detail_lora_name: str = ""
    comfy_upscale_model: str = ""
    pulid_model: str = ""

    strict_offline: bool = False
    require_auth_token: bool = False
    api_token: str = ""

    enable_sdxl: bool = False
    enable_video: bool = False
    enable_captions: bool = False
    enable_external_refs: bool = False
    # Product packaging/product shots for ads — separate from character face refs.
    enable_product_uploads: bool = True

    mock_generation: bool = True

    # Repo root relative workflows
    workflows_dir: Path = Path("./workflows")

    # Ostris AI Toolkit (in-app LoRA train). Empty = auto-detect ~/ai-toolkit.
    ai_toolkit_dir: str = ""
    hf_token: str = ""
    lora_train_steps: int = 1500
    lora_dim: int = 32
    stop_vllm_before_train: bool = True

    def resolved_data_dir(self) -> Path:
        return self.data_dir.resolve()

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def bind_is_public(self) -> bool:
        from instantimpact_common.offline import bind_is_loopback

        return not bind_is_loopback(self.host)

    def flux_runtime(self):
        from instantimpact_common.flux_inventory import FluxRuntime, resolve_comfy_root

        return FluxRuntime(
            mock=self.mock_generation,
            comfy_enabled=self.comfy_enabled,
            loader=(self.comfy_loader or "checkpoint").strip().lower(),
            comfy_root=resolve_comfy_root(self.comfy_dir or None),
            ckpt_name=self.comfy_ckpt_name,
            unet_name=self.comfy_unet_name,
            clip_name1=self.comfy_clip_name1,
            clip_name2=self.comfy_clip_name2,
            vae_name=self.comfy_vae_name,
            detail_lora_name=(self.detail_lora_name or "").strip() or None,
            upscale_model_name=(self.comfy_upscale_model or "").strip() or None,
            pulid_model_name=(self.pulid_model or "").strip() or None,
        )

    def auth_is_required(self) -> bool:
        """Token required when explicitly set, or when LAN-bound with a token configured."""
        if not self.api_token:
            return False
        if self.require_auth_token:
            return True
        return self.bind_is_public()


@lru_cache
def get_settings() -> Settings:
    return Settings()
