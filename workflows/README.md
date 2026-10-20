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

Optional stages (same node ids on every template; the worker drops unused ones):

| Nodes | Stage | Dropped when |
|-------|--------|----------------|
| 12 | Anatomy/realism LoRA | no `DETAIL_LORA_NAME` |
| 15–19 + 14 | Pixel hi-res (decode → optional upscale model → lanczos → encode → low denoise) | `hires_fix` is false |
| 16–17 | `UpscaleModelLoader` + `ImageUpscaleWithModel` | no `UPSCALE_MODEL_NAME` (lanczos only) |
| 30–34 | PuLID-Flux identity | no model filename or no face ref |
| 40–42 | Identity img2img (LoadImage → scale → VAEEncode into sampler 3) | hunt / no locked still; sampler denoise binds `BASE_DENOISE` (1.0 when dropped) |

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

Every other node id matches the fp8 templates, so the detail-LoRA and hi-res bypasses behave identically. Selected by `INSTANTIMPACT_COMFY_LOADER=split`. Point `INSTANTIMPACT_COMFY_UNET_NAME` at `flux1-dev.safetensors` or the photoreal `flux1-krea-dev.safetensors` (see `scripts/bootstrap_models.py --profile krea`).

## `qwen_garment_tryon_v1.json`

Local Qwen Image Edit FP8 post-process for products marked as garments and
placed as `wearing`. The worker uploads a composite containing the generated
person and garment reference, applies exact garment/styling instructions, and
replaces the base still with the edited result. Install with
`scripts/bootstrap_models.py --profile garment`.

## `wan22_5b_i2v_vertical_v1.json`

Wan 2.2 TI2V-5B image-to-video workflow derived from Comfy-Org's official
template. It creates silent 480×832 vertical clips from approved stills and
saves them through core `CreateVideo`/`SaveVideo` nodes. Default length is
121 frames at 16 fps (~8s); 81 (~5s) and 161 (~10s) are valid 4n+1 options.
Studio dresses via `POST .../assets/{id}/dress` (Qwen only, no Flux), then
animates an approved dressed still. A garment product on an undressed still
still runs `qwen_garment_tryon_v1` before this graph. Install with
`scripts/bootstrap_models.py --profile video`.
