# Workflow templates

Application code **never** builds ComfyUI graphs at runtime.

1. Export a working graph from ComfyUI (API format).
2. Replace bindable values with `{{VAR_NAME}}` placeholders.
3. Pin custom node commit SHAs in `docs/model_cards.md`.
4. Health checks fail closed if required nodes are missing.

See design doc § Workflow Template Spec and `instantimpact_comfy.binder`.

## `flux_still_character_v1.json`

Runnable **Flux FP8** graph using `CheckpointLoaderSimple` (matches Comfy-Org `flux1-dev-fp8.safetensors`).

| Placeholder | Role |
|-------------|------|
| `CKPT_NAME` | Checkpoint file in Comfy `models/checkpoints/` |
| `POSITIVE_PROMPT` / `NEGATIVE_PROMPT` | From prompt_engine |
| `SEED` / `WIDTH` / `HEIGHT` / `STEPS` / `CFG` | Sampler + latent |
| `FILENAME_PREFIX` | Comfy SaveImage prefix (worker renames into `data/outputs/`) |

Defaults: CFG **1.0**, steps **28**. No LoRA.

## `flux_still_character_lora_v1.json`

Same as above plus **LoraLoader** (`LORA_NAME`, `LORA_STRENGTH`). Selected automatically when the character version has `pipeline_params.flux.comfy_lora_name` after **Register LoRA**.

## `flux_still_character_split_v1.json` / `flux_still_character_lora_split_v1.json`

**Flux BF16** equivalents. BF16 Flux.1-dev is published as a bare diffusion model — no text encoders, no VAE — so `CheckpointLoaderSimple` returns a null clip and the graph only fails once Comfy executes `CLIPTextEncode`. These templates load each component separately instead.

| Placeholder | Role | Comfy directory |
|-------------|------|-----------------|
| `UNET_NAME` | Diffusion model | `models/diffusion_models/` |
| `UNET_WEIGHT_DTYPE` | `default` keeps bf16; `fp8_e4m3fn` trades quality for VRAM | — |
| `CLIP_NAME1` / `CLIP_NAME2` | CLIP-L and T5-XXL | `models/clip/` |
| `VAE_NAME` | Flux autoencoder | `models/vae/` |

Every other node id matches the fp8 templates, so the detail-LoRA and hi-res bypasses behave identically. Selected by `INSTANTIMPACT_COMFY_LOADER=split`.
