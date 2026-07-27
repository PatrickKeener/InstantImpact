# Model cards & license acknowledgments

**Operator action required before production generation.**

| ID | Role | Source | Approx size | License | SHA-256 | Status |
|----|------|--------|-------------|---------|---------|--------|
| `flux_dev_placeholder` | Flux still base | TBD — pin after bake-off | ~12–24 GB | Check source | TBD | not bootstrapped |
| `character_lora` | Per-character | Local train (AI Toolkit) | ~50–300 MB | derivative | per train | per character |
| `pulid_flux` / `ipadapter_flux` | Identity lock | TBD pin | varies | Check source | TBD | post bootstrap |

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
