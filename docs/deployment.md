# Deployment

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
- Web UI: after open, once in browser console:
  `localStorage.setItem('instantimpact_api_token', '<secret>')`
  or start Vite with `VITE_API_TOKEN=<secret>`.
- Keep **ComfyUI on `127.0.0.1`** so only the local worker can reach it.
- Keep **Redis on `127.0.0.1`** unless you later split hosts.

### Mock vs real GPU

| Mode | When |
|------|------|
| `MOCK_GENERATION=true` | UI/API dev without Comfy |
| `MOCK_GENERATION=false` + Comfy + worker | Production stills on L40S |

---

## Alternative: split chamber + nemesis (not recommended for MVP)

Only if you must keep heavy web/DB load off the GPU box or run many non-GPU services on chamber.

| Host | Runs |
|------|------|
| chamber `10.10.30.184` | API, web, Redis, SQLite metadata |
| nemesis `10.10.101.150` | ComfyUI, worker, models |

**Requires:** shared `data/` mount (SMB/NFS) with **identical paths** on both hosts, Redis on chamber reachable from nemesis, and careful firewall rules.

See historical notes in git history if you need this later; prefer all-in-one until LoRA + Flux path is stable.
