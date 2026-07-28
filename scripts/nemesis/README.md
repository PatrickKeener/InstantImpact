# Nemesis start / stop

**One terminal** — everything runs in the background (nohup). You do not need six SSH sessions.

## Recommended: `scripts/ii`

```bash
cd ~/InstantImpact

# Start API + worker + web + Comfy (all background)
bash scripts/ii start

# Free GPU first (stop docker vllm)
bash scripts/ii start --stop-vllm

# Mock only (no Comfy)
bash scripts/ii start --mock

bash scripts/ii status
bash scripts/ii logs              # Ctrl+C only stops the tail
bash scripts/ii logs worker
bash scripts/ii stop              # stop everything
bash scripts/ii restart
```

You can disconnect SSH after `start`; services keep running.

## Lower-level scripts

```bash
bash scripts/nemesis/up.sh --with-comfy --stop-vllm
bash scripts/nemesis/down.sh --all
bash scripts/nemesis/status.sh
```

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
