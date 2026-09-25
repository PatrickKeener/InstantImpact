# Model cards & license acknowledgments

**Operator action required before production generation.**

| ID | Role | Source | Approx size | License | SHA-256 | Status |
|----|------|--------|-------------|---------|---------|--------|
| `flux1-dev-fp8` | Flux still base (packed checkpoint) | [Comfy-Org/flux1-dev](https://huggingface.co/Comfy-Org/flux1-dev) `flux1-dev-fp8.safetensors` | ~17 GB | BFL / see HF card | operator verify | rollback (`--profile fp8`) |
| `flux1-dev-bf16` | Flux.1-dev UNET (split) | [black-forest-labs/FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) `flux1-dev.safetensors` | 23.8 GB | BFL non-commercial | operator verify | `--profile bf16` |
| `flux1-krea-dev` | Photoreal Flux UNET (split) | [black-forest-labs/FLUX.1-Krea-dev](https://huggingface.co/black-forest-labs/FLUX.1-Krea-dev) `flux1-krea-dev.safetensors` | 23.8 GB | BFL non-commercial | operator verify | **recommended** (`--profile krea`) |
| `clip-l` / `t5xxl-fp16` / `ae` | Flux text encoders + VAE | [comfyanonymous/flux_text_encoders](https://huggingface.co/comfyanonymous/flux_text_encoders) + BFL `ae.safetensors` | ~10.4 GB | mixed | operator verify | required with split loader |
| `character_lora` | Per-character | Local train (AI Toolkit) | ~50–300 MB | derivative | per train | per character |
| `pulid_flux` | Flux identity adapter | [ByteDance PuLID-FLUX](https://huggingface.co/guozinan/PuLID) `pulid_flux_v0.9.1.safetensors` | ~1 GB | see HF card | operator verify | optional; Studio / `INSTANTIMPACT_PULID_MODEL` |
| `upscale_model` | Pixel hi-res | e.g. `4x-UltraSharp.pth` in Comfy `models/upscale_models` | ~50–100 MB | see source | operator verify | optional; lanczos if unset |

**Bootstrap (setup, networked):** `python scripts/bootstrap_models.py --profile krea --i-accept-licenses`  
Requires `INSTANTIMPACT_COMFY_DIR` and, for gated BFL files, `INSTANTIMPACT_HF_TOKEN` after you accept the license on Hugging Face.

**Comfy path (split / Krea):** UNET in `models/diffusion_models/`, CLIP/T5 in `models/clip/` or `models/text_encoders/`, VAE in `models/vae/`. Packed FP8 rollback still uses `models/checkpoints/`.

Phased still-quality work (CFG, CLIP-L, checkpoint swap, detail LoRA, pixel hi-res, PuLID): [`docs/quality-phases.md`](quality-phases.md).

## Swapping the still base checkpoint

Stock Flux.1-dev was trained on a filtered dataset, so its prior for bare
anatomy is weak. Prompting and the hi-res pass can sharpen what the model
already knows but cannot add a prior that is absent from the weights. Swapping
the base checkpoint is the only fix at the source.

Nothing in the graph is pinned to a specific checkpoint — `CKPT_NAME` is a bound
placeholder — so a swap is configuration, not code:

| Setting | Controls | Default |
|---|---|---|
| `INSTANTIMPACT_COMFY_CKPT_NAME` | Checkpoint the sampler loads | `flux1-dev-fp8.safetensors` |
| `INSTANTIMPACT_TRAIN_BASE_MODEL` | Base the character LoRA trains against | `black-forest-labs/FLUX.1-dev` |

**Keep these two matched.** A LoRA is a delta against the weights it was trained
on, so training against stock FLUX.1-dev while sampling from a finetune costs
identity fidelity. The stock config trains in bf16 but samples fp8, which is
already a mild version of this mismatch.

Constraints when choosing a replacement:

- Must stay Flux-architecture to keep `CLIPTextEncodeFlux` and existing
  character LoRAs loadable. Non-Flux bases (SDXL-derived) require a graph
  rewrite and a LoRA retrain.
- Guidance-distilled bases (stock Flux.1-dev) require KSampler `cfg` 1.0, which
  makes `NEGATIVE_PROMPT` inert. De-distilled bases accept real CFG, so raising
  `FluxPipelineParams.cfg` to ~3–4 makes the negative list live again. Node `7`
  already encodes it and feeds both samplers.
- L40S (48 GB) fits bf16 Flux (~24 GB) plus two LoRAs and the hi-res pass, so
  prefer bf16 over fp8 for fine detail.

Record whatever you land on in the table above with its license and checksum
before production generation.

## Disk budget (MVP path)

| Component | Rough size |
|-----------|------------|
| Flux base + text encoders + VAE | 20–40 GB |
| Identity adapter nodes/weights | 1–5 GB |
| Ollama (post-MVP captions) | 5–15 GB |
| Character datasets + outputs | grows with use |

**Minimum free disk before train/batch:** recommend **50 GB** free for MVP still path.

## Setup vs runtime

- **Setup:** network allowed with user-confirmed downloads + checksum verify.
- **Runtime:** offline; `INSTANTIMPACT_STRICT_OFFLINE=true` fails outbound attempts.

## Acknowledgment

Bootstrap must record operator acknowledgment timestamp in `app_settings` before marking models ready.
