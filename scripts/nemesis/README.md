# Nemesis start / stop

Easy bring-up and teardown for InstantImpact on **nemesis** (Linux).  
Reuses your existing `.venv`, `data/`, and optional host **ComfyUI** — no need to rebuild models.

## One-liners

```bash
cd ~/InstantImpact

# Start app (API + worker + web). Starts docker redis if nothing on 6379.
./scripts/nemesis/up.sh

# Start app + ComfyUI from ~/ComfyUI
./scripts/nemesis/up.sh --with-comfy

# Free GPU for Flux (stops docker container named vllm)
./scripts/nemesis/up.sh --with-comfy --stop-vllm

# Mock only (no Comfy needed)
./scripts/nemesis/up.sh --mock

# Status
./scripts/nemesis/status.sh

# Stop InstantImpact processes
./scripts/nemesis/down.sh

# Stop app + Comfy we started + our docker redis
./scripts/nemesis/down.sh --all
```

First time: `chmod +x scripts/nemesis/*.sh`

## What starts / stops

| Component | `up.sh` | `down.sh` | `down.sh --all` |
|-----------|---------|-----------|-----------------|
| API :8001 | yes | yes | yes |
| Worker | yes | yes | yes |
| Web :5173 | yes | yes | yes |
| Redis | start docker if missing | no* | stops `instantimpact-redis` only |
| ComfyUI | only with `--with-comfy` | only with `--with-comfy` | yes |
| vLLM / Ollama | only with `--stop-vllm` on up | never | never |

\* System `redis-server` from apt is left running (shared). Docker `instantimpact-redis` is stopped only with `--redis` or `--all`.

## Logs & PIDs

```text
.run/pids/     # process ids
.run/logs/     # api.log worker.log web.log comfy.log
```

```bash
tail -f .run/logs/worker.log
tail -f .run/logs/api.log
```

## UI

- http://10.10.101.150:5173  
- Token once in browser console:

```js
localStorage.setItem('instantimpact_api_token', '<from .env>')
```

## Docker alternative

If you prefer containers for **app only** (Comfy still on host):

```bash
docker compose up -d --build
docker compose down
```

See root `docker-compose.yml`. Prefer `scripts/nemesis/up.sh` on this machine — it matches how you already run Comfy + venv.
