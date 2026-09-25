# Character LoRA (identity lock)

Goal: stop face drift / cartoon variance by training a **per-character Flux LoRA** on approved photoreal stills, then using it on every still job.

## One-click (recommended)

1. Approve 12–30 photoreal stills in Studio.
2. Click **Train LoRA & register**.
3. Wait for the `lora_train` job (GPU exclusive, typically 20–90 minutes on L40S).
4. On success the worker writes `model.safetensors` and the API registers it into Comfy.
5. Lock the character, then generate.

Requires:

- Native **GPU worker** (`python -m worker.main` / `bash scripts/ii start`), not the Docker CPU worker
- Ostris AI Toolkit at `INSTANTIMPACT_AI_TOOLKIT_DIR` (default `/home/pkeener/ai-toolkit`)
- Hugging Face login with **FLUX.1-dev** license (`INSTANTIMPACT_HF_TOKEN` or `HF_TOKEN`)
- Free GPU: the job runs `docker stop vllm` and Comfy `/free` before training

```bash
# one-time toolkit install (as pkeener, not root)
git clone https://github.com/ostris/ai-toolkit.git /home/pkeener/ai-toolkit
cd /home/pkeener/ai-toolkit
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
huggingface-cli login
```

If Compose is running the worker container, stop it so the native worker owns the queue:

```bash
docker stop instantimpact-worker
cd /home/pkeener/InstantImpact/apps/worker
# env from repo .env
../../.venv/bin/python -m worker.main
```

## Manual fallback

1. **Build dataset only** in Studio.
2. `./scripts/nemesis/train_lora_hint.sh <character_id>`
3. Train with AI Toolkit using the printed paths.
4. Studio → **Register LoRA** with the `.safetensors` path.

## Suggested train settings

| Setting | Value |
|---------|--------|
| Base | Flux (`black-forest-labs/FLUX.1-dev`) |
| Network | LoRA dim 32, alpha 32 |
| Steps | 1500 (UI 200–4000) |
| LR | 1e-4 |
| Res | 512 / 768 / 1024 |

## Comfy env

```text
INSTANTIMPACT_COMFY_LORAS_DIR=/home/pkeener/ComfyUI/models/loras
INSTANTIMPACT_AI_TOOLKIT_DIR=/home/pkeener/ai-toolkit
```
