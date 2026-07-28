# InstantImpact

**Local AI Persona Content Studio** — design synthetic adult (21+) personas, lock visual identity (Flux + LoRA), batch stills, review & export. Runs offline on your machine (reference: Windows 11 + NVIDIA L40S 48GB).

> Discreet, legal, synthetic-only. No real-person scrape/clone tools. External photo refs are disabled in MVP.

## Design

Full architecture, consistency strategy, and PR plan:

- [`docs/design-instantimpact.md`](docs/design-instantimpact.md)

## Frozen MVP

| In | Out (later) |
|----|-------------|
| Character Creator | Short video (I2V) |
| Flux still consistency path | Ollama captions |
| Seed gallery + batch stills | SDXL dual pipeline |
| Review / approve | Fanvue API |
| Mock gen + ComfyUI hooks | Kohya fallback |

## Where to run it

**Recommended: everything on nemesis** (`10.10.101.150`, L40S).  
chamber (`10.10.30.184`) is fine as a **browser only** — open the nemesis UI from there.

See [`docs/deployment.md`](docs/deployment.md).

### Easy start / stop (Linux / nemesis) — one terminal

```bash
cd ~/InstantImpact

bash scripts/ii start --stop-vllm   # API + worker + web + Comfy (background)
bash scripts/ii status
bash scripts/ii logs                # optional; Ctrl+C keeps services running
bash scripts/ii stop                # when done
```

No multi-terminal setup. Details: [`scripts/nemesis/README.md`](scripts/nemesis/README.md).  
Optional Docker (app only): `docker compose up -d` / `docker compose down`.

## Quick start (on nemesis)

```powershell
# From repo root on nemesis
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.nemesis.example .env
# Set INSTANTIMPACT_API_TOKEN in .env

# API (LAN)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload --host 0.0.0.0 --port 8000

# Web (second terminal)
cd apps\web
npm install
npm run dev
```

Open **http://10.10.101.150:5173** (from chamber or any LAN client), or localhost on nemesis.

Or run `.\scripts\dev_up.ps1` for setup hints.

### Mock vs real GPU

- Default: `INSTANTIMPACT_MOCK_GENERATION=true` — placeholder stills so the UI/API work without ComfyUI.
- **Real Flux:** ComfyUI on `127.0.0.1:8188` with `flux1-dev-fp8.safetensors`, Redis + worker, then in `.env`:
  `INSTANTIMPACT_MOCK_GENERATION=false`, `INSTANTIMPACT_COMFY_ENABLED=true`.
  See [`docs/deployment.md`](docs/deployment.md) § Real Flux stills.

## Layout

```
apps/api          FastAPI control plane (sole SQLite writer)
apps/web          React + Vite dashboard
apps/worker       ARQ GPU worker (no SQLite)
packages/common   Schemas, safety, paths
packages/comfy_client  Workflow binder + Comfy HTTP client
packages/prompt_engine Flux prompt contract renderer
workflows/        Versioned Comfy templates
data/             gitignored DB + media
docs/             design, safety, model cards
```

## Safety

- Age appearance **≥ 21** (schema + deny-lists)
- Synthetic + not-real-person attestations required before gen
- Generate-only references in MVP
- Disclosure sidecars on every asset

See [`docs/safety.md`](docs/safety.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## License

Private / local use. You are responsible for model licenses, platform ToS, and local law. Model pins and license notes live in `docs/model_cards.md`.
