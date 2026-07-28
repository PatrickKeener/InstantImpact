# Character LoRA (identity lock)

Goal: stop face drift / cartoon variance by training a **per-character Flux LoRA** on approved photoreal stills, then using it on every still job.

## Workflow in InstantImpact

1. **Generate** seed + batch stills (photoreal prompts).
2. **Approve** 12–30 best faces/bodies (reject cartoons, bad anatomy).
3. Studio → **Build training set from approved**  
   - Copies images → `data/characters/{id}/versions/vNNN/dataset/`  
   - Writes `.txt` captions with **trigger word**  
   - Writes `…/lora/train_config.json`  
   - Character status → `training` (first-time path)
4. **Train** outside the app (GPU exclusive):
   ```bash
   ./scripts/nemesis/train_lora_hint.sh <character_id>
   # then Ostris AI Toolkit (or compatible Flux LoRA trainer)
   docker stop vllm   # free L40S
   ```
5. Studio → **Register LoRA** with absolute path to `.safetensors`  
   - Installs as `ii_{slug}_vNNN.safetensors` under `~/ComfyUI/models/loras/`  
   - Stores strength + `comfy_lora_name` on the version
6. **Restart/refresh Comfy** so it sees the new LoRA file.
7. **Lock** character (edit → safety lock) when happy with validation stills.
8. **Batch stills** — worker auto-selects `flux_still_character_lora_v1.json` and injects trigger + LoRA.

## Suggested train settings (starting point)

| Setting | Value |
|---------|--------|
| Base | Flux (same family as `flux1-dev-fp8` / full Dev) |
| Network | LoRA dim 16–32, alpha = dim |
| Steps | ~1000–2500 |
| LR | ~1e-4 |
| Res | 1024 |
| Captions | Trigger first; describe **what changes** (pose, outfit), not the whole face every time |

Exact YAML depends on your AI Toolkit version — use `train_config.json` paths as the source of truth for dataset/output.

## Comfy env

```text
INSTANTIMPACT_COMFY_LORAS_DIR=/home/pkeener/ComfyUI/models/loras
```

Default is `~/ComfyUI/models/loras`.

## Notes

- Training is **not** fully automated inside InstantImpact yet (AI Toolkit process is external). Dataset + register + generate **are** integrated.
- LoRA strength default **0.85** (adjust on register).
- Without a registered LoRA, generation uses the base FP8 workflow only.
