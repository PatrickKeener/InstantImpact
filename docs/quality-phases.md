# Still quality — phased rollout

Work one phase at a time. Later phases assume the earlier ones are in place.

| Phase | Who | Goal | Status |
|-------|-----|------|--------|
| **1** | Code + you | Unblock quality knobs. CLIP-L carries identity. CFG is honored. Studio can set detail LoRA / denoise. | Done |
| **2** | Code + you | Swap still checkpoint to bf16 Flux, then FLUX.1-Krea-dev photoreal UNET. Bootstrap + health fail-closed. Match train base. | Done (download on host) |
| **3** | You | Install an anatomy/realism LoRA, set `detail_lora_name`, generate a comparison batch. Retrain character LoRAs after the checkpoint swap. | Host |
| **4** | Code | Pixel upscaler instead of latent `nearest-exact`. | Done |
| **5** | Code | PuLID-Flux from the generate-only ref pack. | Done (optional) |
| **6** | Code | Training captions + LoRA dim + face-score review. | Done |

## Phase 1 (done in app code)

You do **not** need a new checkpoint for Phase 1 to land. Defaults stay safe for stock distilled Flux.1-dev (`cfg` 1.0).

What changed:

- Worker reads `pipeline_params.flux.cfg` (clamped 1–8) instead of forcing 1.0.
- CLIP-L now includes hair/eyes/body **before** location and product text.
- Studio → **Still quality** saves CFG, guidance, steps, hi-res, and detail LoRA on the character version (merge, so registered character LoRA is not wiped).
- Optional host-wide detail LoRA: `INSTANTIMPACT_DETAIL_LORA_NAME` (filename in Comfy `models/loras`). Per-character Studio value wins.

## Phase 2 — checkpoint (done in app; download on the GPU host)

Stay on **Flux architecture** so existing graphs and LoRAs load. SDXL is a later rewrite.

App support:

- `python scripts/bootstrap_models.py --profile krea --i-accept-licenses` downloads the photoreal UNET + shared CLIP/T5/VAE into `INSTANTIMPACT_COMFY_DIR`.
- Profiles: `fp8` (rollback), `bf16` (stock Flux precision), `krea` (recommended photoreal on L40S), `krea-fp8` (VRAM fallback).
- `GET /api/system/health` → `pipelines.flux_still` (`ok` / `mock` / `missing_weights` / `missing_nodes` / `unreachable`).
- Still enqueue **fails closed** (HTTP 503) when required files are missing under `INSTANTIMPACT_COMFY_DIR`.
- Dashboard shows a missing-weights banner with the bootstrap command.

**Recommended on nemesis (48 GB):** `--profile krea` then:

```text
INSTANTIMPACT_COMFY_LOADER=split
INSTANTIMPACT_COMFY_UNET_NAME=flux1-krea-dev.safetensors
INSTANTIMPACT_COMFY_CLIP_NAME1=clip_l.safetensors
INSTANTIMPACT_COMFY_CLIP_NAME2=t5xxl_fp16.safetensors
INSTANTIMPACT_COMFY_VAE_NAME=ae.safetensors
INSTANTIMPACT_TRAIN_BASE_MODEL=black-forest-labs/FLUX.1-Krea-dev
```

Krea is a drop-in Flux-architecture UNET. Keep sampler CFG at 1.0 until you confirm stills; then try 3–4 only if the card wants it. **Retrain every character LoRA** after this swap.

BF16 Flux.1-dev and Krea are **bare diffusion models** (no CLIP, no VAE). Do not drop them into `models/checkpoints/` — `CheckpointLoaderSimple` would hand CLIP a null clip. Use `INSTANTIMPACT_COMFY_LOADER=split`.

Rollback: `INSTANTIMPACT_COMFY_LOADER=checkpoint` returns to the fp8 templates.

Budget about **34 GB** of VRAM (23.8 UNET + 9.8 T5). On a 48 GB L40S stop other GPU tenants first, or set `INSTANTIMPACT_COMFY_CLIP_NAME2=t5xxl_fp8_e4m3fn.safetensors` to save ~5 GB.

## Phase 3 — detail LoRA + retrain

1. Place an anatomy/realism Flux LoRA in `ComfyUI/models/loras/`.
2. Either set `INSTANTIMPACT_DETAIL_LORA_NAME=thatfile.safetensors` or paste the filename in Studio → Still quality → save.
3. Start at strength **0.6**.
4. After a checkpoint swap, **retrain every character LoRA** (Studio → Train LoRA & register). Old LoRAs are deltas against the previous base.

If faces look locked at base size and smear after the second pass, drop **hi-res denoise** to 0.25–0.35 before raising character LoRA strength.

## Phase 4 — pixel hi-res (done)

The second pass no longer uses `LatentUpscale` `nearest-exact`. It decodes the base latent, optionally runs an upscale model (`ImageUpscaleWithModel`), lanczos-scales to the target size, encodes, then samples at low denoise.

- Empty upscale model (default): lanczos `ImageScale` only. Still sharper than latent nearest-exact, no extra weights.
- Set `INSTANTIMPACT_COMFY_UPSCALE_MODEL=4x-UltraSharp.pth` (file in Comfy `models/upscale_models`) or paste the filename in Studio → Still quality.
- After a 4× model the graph scales down to the 1.5× target so VRAM stays bounded.

## Phase 5 — PuLID-Flux (done, optional)

Identity lock from the generate-only ref pack. Off unless a model filename is set **and** a face still exists under the version `refs/` folder (`face_primary.png` preferred).

1. Install [ComfyUI-PuLID-Flux](https://github.com/balazik/ComfyUI-PuLID-Flux) (or a fork that keeps `ApplyPulidFlux` / `PulidFluxModelLoader` class names).
2. Place `pulid_flux_v0.9.1.safetensors` (or the current ByteDance Flux PuLID file) in `ComfyUI/models/pulid/`.
3. Set `INSTANTIMPACT_PULID_MODEL=pulid_flux_v0.9.1.safetensors` or paste the filename in Studio.
4. Build a dataset once so `refs/face_primary.png` exists, or copy a front face still there.
5. Start at strength **0.7**. InsightFace provider defaults to `CUDA`; set `INSTANTIMPACT_PULID_PROVIDER=CPU` if needed.

The worker uploads the face ref to Comfy's input folder and drops the PuLID subgraph when the model or ref is missing, so stock Comfy without those custom nodes keeps working.

IP-Adapter strength remains on `FluxPipelineParams` for a later SDXL / Flux-Redux path.

## Phase 6 — train captions, dim 32, review score (done)

- Dataset captions are trigger + pose/light/outfit/crop. Hair/eyes/body are not restated so the LoRA does not require those tokens at inference.
- Default LoRA dim is **32** (`INSTANTIMPACT_LORA_DIM` / `lora_dim` setting).
- Review score is a face-weighted dHash + color histogram on the upper-center crop. InsightFace cosine similarity is used when that package is installed. Studio Outputs can sort by **best match**.

See also `docs/model_cards.md` (swap rules) and `docs/lora-training.md`.
