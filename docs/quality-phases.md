# Still quality — phased rollout

Work one phase at a time. Later phases assume the earlier ones are in place.

| Phase | Who | Goal |
|-------|-----|------|
| **1** | Code + you | Unblock quality knobs. CLIP-L carries identity. CFG is honored. Studio can set detail LoRA / denoise. |
| **2** | You (GPU host) | Swap still checkpoint to bf16 Flux, then a Flux-arch photoreal finetune. Match train base. Pin license + SHA. |
| **3** | You | Install an anatomy/realism LoRA, set `detail_lora_name`, generate a comparison batch. Retrain character LoRAs after the checkpoint swap. |
| **4** | Code | Pixel upscaler instead of latent `nearest-exact`. |
| **5** | Code | PuLID / IP-Adapter from the generate-only ref pack. |
| **6** | Code | Training captions + LoRA dim + face-score review. |

## Phase 1 (done in app code)

You do **not** need a new checkpoint for Phase 1 to land. Defaults stay safe for stock distilled Flux.1-dev (`cfg` 1.0).

What changed:

- Worker reads `pipeline_params.flux.cfg` (clamped 1–8) instead of forcing 1.0.
- CLIP-L now includes hair/eyes/body **before** location and product text.
- Studio → **Still quality** saves CFG, guidance, steps, hi-res, and detail LoRA on the character version (merge, so registered character LoRA is not wiped).
- Optional host-wide detail LoRA: `INSTANTIMPACT_DETAIL_LORA_NAME` (filename in Comfy `models/loras`). Per-character Studio value wins.

## Phase 2 — checkpoint (your machine)

Stay on **Flux architecture** so existing graphs and LoRAs load. SDXL is a later rewrite.

BF16 Flux.1-dev is **not** a drop-in replacement for the fp8 file. Black Forest Labs publishes it as a bare diffusion model: no CLIP-L, no T5-XXL, no VAE. Dropping it into `models/checkpoints/` and pointing `INSTANTIMPACT_COMFY_CKPT_NAME` at it makes `CheckpointLoaderSimple` hand `CLIPTextEncode` a null clip, Comfy accepts the prompt over HTTP and then fails at execution with `clip input is invalid: None`. Use the split-loader path instead.

1. Put each component in its own Comfy directory:

| File | Directory | Size |
|------|-----------|------|
| `flux1-dev.safetensors` | `models/diffusion_models/` | 23.8 GB |
| `clip_l.safetensors` | `models/clip/` | 246 MB |
| `t5xxl_fp16.safetensors` | `models/clip/` | 9.8 GB |
| `ae.safetensors` | `models/vae/` | 335 MB |

2. Set in `.env`:

```text
INSTANTIMPACT_COMFY_LOADER=split
INSTANTIMPACT_COMFY_UNET_NAME=flux1-dev.safetensors
INSTANTIMPACT_COMFY_CLIP_NAME1=clip_l.safetensors
INSTANTIMPACT_COMFY_CLIP_NAME2=t5xxl_fp16.safetensors
INSTANTIMPACT_COMFY_VAE_NAME=ae.safetensors
INSTANTIMPACT_TRAIN_BASE_MODEL=matched-hf-id-or-local-path
```

3. Record license + SHA-256 in `docs/model_cards.md`.
4. Restart ComfyUI so it rescans the model directories, then restart the GPU worker so it picks up the env.
5. Generate a small portrait batch **before** raising CFG.

Rollback is one key: `INSTANTIMPACT_COMFY_LOADER=checkpoint` returns to the fp8 templates.

Budget about **34 GB** of VRAM (23.8 UNET + 9.8 T5). On a 48 GB L40S that fits only with the card otherwise idle — stop other GPU tenants first, or set `INSTANTIMPACT_COMFY_CLIP_NAME2=t5xxl_fp8_e4m3fn.safetensors` to save ~5 GB at a small prompt-fidelity cost.

**Keep sampler CFG at 1.0** until the new card is de-distilled. Distilled Flux still ignores negatives at CFG 1. If the card says it wants CFG, raise it in Studio to ~3–4 after you confirm stills still look like Flux (not fried).

L40S 48 GB: prefer bf16 over the current fp8 pin.

## Phase 3 — detail LoRA + retrain

1. Place an anatomy/realism Flux LoRA in `ComfyUI/models/loras/`.
2. Either set `INSTANTIMPACT_DETAIL_LORA_NAME=thatfile.safetensors` or paste the filename in Studio → Still quality → save.
3. Start at strength **0.6**.
4. After a checkpoint swap, **retrain every character LoRA** (Studio → Train LoRA & register). Old LoRAs are deltas against the previous base.

If faces look locked at base size and smear after the second pass, drop **hi-res denoise** to 0.25–0.35 before raising character LoRA strength.

## Later phases (not started)

- **4:** Replace `LatentUpscale` `nearest-exact` with decode → upscale model → encode → low denoise.
- **5:** Wire PuLID-Flux / IP-Adapter; schema already has the strength fields.
- **6:** Captions that describe pose/light/outfit only; LoRA dim 32; real face similarity in review.

See also `docs/model_cards.md` (swap rules) and `docs/lora-training.md`.
