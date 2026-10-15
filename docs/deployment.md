# Deployment

## Easy start / stop (recommended day-to-day)

On nemesis, InstantImpact itself runs native. Ollama, Nemotron OCR, and vLLM stay in Docker and are paused only while a job owns the GPU.

```bash
cd ~/InstantImpact

# One time: start on boot as pkeener
sudo bash scripts/ii install-service
sudo systemctl start instantimpact

# Day to day
bash scripts/ii status
bash scripts/ii logs
sudo systemctl stop instantimpact

# After pulling fixes
bash scripts/ii update
```

`bash scripts/ii start` still works without systemd. It disables the Docker API/worker/web containers so they cannot take the GPU queue. Logs: `.run/logs/`. See `scripts/nemesis/README.md`.

---

## Recommended: all-in-one on **nemesis** (L40S)

| Host | IP | Role |
|------|-----|------|
| **nemesis** | `10.10.101.150` | API, web UI, Redis, SQLite, ComfyUI, worker, models, `data/` |
| **chamber** | `10.10.30.184` | Optional — browser only (open nemesis URLs), or later secondary services |

**Why nemesis is better for InstantImpact**

1. **GPU and files stay local** — ComfyUI, LoRAs, refs, and outputs never cross the network.
2. **No shared filesystem** — split chamber/nemesis needs SMB/NFS for `data/`; all-in-one does not.
3. **Lower latency / fewer failure modes** — Redis, worker, and Comfy on one box.
4. **VRAM lifecycle is local** — train and stills contend for one L40S without remote path bugs.
5. **Matches the design’s “single GPU workstation” model.**

Use **chamber only as a client** (browse `http://10.10.101.150:5173` or `:8000` from chamber or your PC).

```text
[You / chamber browser]
        |
        v
   nemesis 10.10.101.150
   ├── web  :5173
   ├── API  :8000
   ├── Redis :6379
   ├── ComfyUI :8188 (prefer 127.0.0.1 only)
   └── worker + L40S + data/
```

### nemesis quick start

```powershell
# On nemesis
cd <repo>
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.nemesis.example .env
# Edit .env: set a strong INSTANTIMPACT_API_TOKEN

# Redis on localhost (Windows: Memurai / Redis, or WSL redis-server)

# Terminal 1 — API (LAN so chamber can open UI)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --host 0.0.0.0 --port 8000

# Terminal 2 — Web
cd apps\web
npm install
npm run dev -- --host 0.0.0.0 --port 5173

# Terminal 3 — Worker (when not using mock)
$env:INSTANTIMPACT_REDIS_URL="redis://127.0.0.1:6379/0"
.\.venv\Scripts\python.exe -m worker.main

# Terminal 4 — ComfyUI (real gen)
# python main.py --listen 127.0.0.1 --port 8188
```

Open from any LAN machine:

- UI: `http://10.10.101.150:5173`
- API docs: `http://10.10.101.150:8000/docs`

### Security (adult library on LAN)

- Bind API/web to `0.0.0.0` only on trusted VLAN `10.10.x.x`.
- Set `INSTANTIMPACT_REQUIRE_AUTH_TOKEN=true` and a long `INSTANTIMPACT_API_TOKEN`.
- Web UI: click **token** in the header and save, or once in the browser console:
  `localStorage.setItem('instantimpact_api_token', '<secret>')`
  or start Vite with `VITE_API_TOKEN=<secret>`.
- Binding `0.0.0.0` with a token configured **auto-enables** auth even if `REQUIRE_AUTH_TOKEN` is false.
- Native Vite default proxy is port **8000**. Nemesis `up.sh` sets `VITE_API_PROXY` to the API port (8001 when vLLM owns 8000).
- Keep **ComfyUI on `127.0.0.1`** so only the local worker can reach it.
- Keep **Redis on `127.0.0.1`** unless you later split hosts.

### Mock vs real GPU

| Mode | When |
|------|------|
| `MOCK_GENERATION=true` | UI/API dev without Comfy |
| `MOCK_GENERATION=false` + Comfy + worker | Production stills on L40S |

### Real Flux stills (Comfy integration)

Prerequisites on **nemesis**:

1. Redis running (`redis-cli ping` → PONG)
2. ComfyUI on `127.0.0.1:8188` with `flux1-dev-fp8.safetensors` in `ComfyUI/models/checkpoints/`
3. InstantImpact `.env`:

```text
INSTANTIMPACT_MOCK_GENERATION=false
INSTANTIMPACT_COMFY_ENABLED=true
INSTANTIMPACT_COMFY_URL=http://127.0.0.1:8188
INSTANTIMPACT_COMFY_CKPT_NAME=flux1-dev-fp8.safetensors
INSTANTIMPACT_REDIS_URL=redis://127.0.0.1:6379/0
```

4. Start processes (separate terminals / tmux):

```bash
# API (example port 8001 if vLLM owns 8000)
cd ~/InstantImpact
.venv/bin/python -m uvicorn app.main:app --app-dir apps/api --reload --host 0.0.0.0 --port 8001

# Worker — must see Comfy + workflows + data
cd ~/InstantImpact/apps/worker
export INSTANTIMPACT_REDIS_URL=redis://127.0.0.1:6379/0
export INSTANTIMPACT_COMFY_URL=http://127.0.0.1:8188
export INSTANTIMPACT_COMFY_CKPT_NAME=flux1-dev-fp8.safetensors
export INSTANTIMPACT_DATA_DIR=/home/pkeener/InstantImpact/data
export INSTANTIMPACT_WORKFLOWS_DIR=/home/pkeener/InstantImpact/workflows
../../.venv/bin/python -m worker.main

# Web
cd ~/InstantImpact/apps/web
VITE_API_PROXY=http://127.0.0.1:8001 npm run dev -- --host 0.0.0.0 --port 5173
```

5. Free GPU for Flux if needed: `docker stop vllm`

6. In the UI: seed gallery / batch stills → jobs go **Queued → Running → Completed** with real images (not MOCK STILL placeholders).

Workflow template: `workflows/flux_still_character_v1.json` (CheckpointLoaderSimple FP8 path).

### Garment references and vertical marketing video

Install the optional local model profiles once on nemesis:

```bash
cd /home/pkeener/InstantImpact
.venv/bin/python scripts/bootstrap_models.py --profile garment --i-accept-licenses
.venv/bin/python scripts/bootstrap_models.py --profile video --i-accept-licenses
```

The garment profile installs Qwen Image Edit FP8 plus its vision encoder, VAE,
and four-step LoRA (about 29 GB total). The video profile installs Wan 2.2
TI2V-5B, UMT5 FP8, and the Wan VAE (about 19 GB total). Uploaded clothing is
used as a visual reference after the FLUX character still is generated. Exact
logos, typography, seams, and patterns still require human review.

Enable video in the existing `.env` and restart:

```text
INSTANTIMPACT_ENABLE_VIDEO=true
INSTANTIMPACT_VIDEO_TIMEOUT=3600
```

```bash
bash scripts/ii restart
```

Video output is a silent 480×832 MP4, 81 frames at 16 fps (about five seconds).
Generation uses the same exclusive GPU handoff as stills. Keep the silent
master for later voice, captions, audio muxing, and lip sync.

---

## Alternative: split chamber + nemesis (not recommended for MVP)

Only if you must keep heavy web/DB load off the GPU box or run many non-GPU services on chamber.

| Host | Runs |
|------|------|
| chamber `10.10.30.184` | API, web, Redis, SQLite metadata |
| nemesis `10.10.101.150` | ComfyUI, worker, models |

**Requires:** shared `data/` mount (SMB/NFS) with **identical paths** on both hosts, Redis on chamber reachable from nemesis, and careful firewall rules.

See historical notes in git history if you need this later; prefer all-in-one until LoRA + Flux path is stable.
