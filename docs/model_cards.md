# Model cards & license acknowledgments

**Operator action required before production generation.**

| ID | Role | Source | Approx size | License | SHA-256 | Status |
|----|------|--------|-------------|---------|---------|--------|
| `flux1-dev-fp8` | Flux still base (Comfy checkpoint) | [Comfy-Org/flux1-dev](https://huggingface.co/Comfy-Org/flux1-dev) `flux1-dev-fp8.safetensors` | ~17 GB | BFL / see HF card | operator verify | **pinned for nemesis MVP** |
| `character_lora` | Per-character | Local train (AI Toolkit) | ~50–300 MB | derivative | per train | per character |
| `pulid_flux` / `ipadapter_flux` | Identity lock | TBD pin | varies | Check source | TBD | post bootstrap |

**Comfy path:** place checkpoint in `ComfyUI/models/checkpoints/`. App setting: `INSTANTIMPACT_COMFY_CKPT_NAME=flux1-dev-fp8.safetensors`. Workflow: `workflows/flux_still_character_v1.json`.

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
