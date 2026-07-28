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
