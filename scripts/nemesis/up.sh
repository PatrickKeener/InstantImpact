#!/usr/bin/env bash
# Bring InstantImpact stack up on nemesis (API + worker + web [+ optional Comfy]).
#
# Usage:
#   ./scripts/nemesis/up.sh              # app stack only (expects Comfy already if real gen)
#   ./scripts/nemesis/up.sh --with-comfy # also start ComfyUI from $COMFY_DIR
#   ./scripts/nemesis/up.sh --mock      # force mock generation for this session
#   ./scripts/nemesis/up.sh --stop-vllm # docker stop vllm to free GPU
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

WITH_COMFY=0
FORCE_MOCK=0
STOP_VLLM=0

for arg in "$@"; do
  case "$arg" in
    --with-comfy) WITH_COMFY=1 ;;
    --mock) FORCE_MOCK=1 ;;
    --stop-vllm) STOP_VLLM=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

load_dotenv
ensure_run_dirs

echo "== InstantImpact up =="
echo "  root: ${ROOT}"
echo "  api:  http://${API_HOST}:${API_PORT}  (LAN: http://10.10.101.150:${API_PORT})"
echo "  web:  http://0.0.0.0:${WEB_PORT}      (LAN: http://10.10.101.150:${WEB_PORT})"
echo ""

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: missing venv at ${ROOT}/.venv — run:"
  echo "  cd ${ROOT} && python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "WARN: no .env — copying .env.nemesis.example"
  cp "${ROOT}/.env.nemesis.example" "${ROOT}/.env"
  echo "  Edit ${ROOT}/.env and set INSTANTIMPACT_API_TOKEN before using the UI."
fi

if [[ "$STOP_VLLM" -eq 1 ]]; then
  if command -v docker >/dev/null 2>&1; then
    echo "  → docker stop vllm (free GPU)"
    docker stop vllm 2>/dev/null || echo "    (vllm container not running or not named vllm)"
  fi
fi

# Redis
if redis_ok; then
  echo "  · redis OK"
else
  echo "  → redis not responding — trying docker redis (instantimpact-redis)"
  if command -v docker >/dev/null 2>&1; then
    if docker ps -a --format '{{.Names}}' | grep -qx instantimpact-redis; then
      docker start instantimpact-redis >/dev/null
    else
      docker run -d --name instantimpact-redis --restart unless-stopped \
        -p 127.0.0.1:6379:6379 redis:7-alpine >/dev/null
    fi
    sleep 1
    if redis_ok; then
      echo "    redis up via docker"
    else
      echo "ERROR: could not start redis. Install redis-server or fix Docker."
      exit 1
    fi
  else
    echo "ERROR: redis not running. Install: sudo apt install -y redis-server"
    exit 1
  fi
fi

# Comfy (optional start)
if [[ "$WITH_COMFY" -eq 1 ]]; then
  if http_ok "${COMFY_URL}/system_stats"; then
    echo "  · comfy already healthy at ${COMFY_URL}"
  else
    if [[ ! -d "$COMFY_DIR" ]]; then
      echo "ERROR: COMFY_DIR not found: ${COMFY_DIR}"
      exit 1
    fi
    COMFY_PY="${COMFY_DIR}/.venv/bin/python"
    if [[ ! -x "$COMFY_PY" ]]; then
      COMFY_PY="python3"
    fi
    start_bg comfy \
      bash -c "cd '${COMFY_DIR}' && exec '${COMFY_PY}' main.py --listen 127.0.0.1 --port 8188"
    echo "    waiting for Comfy..."
    for _ in $(seq 1 60); do
      http_ok "${COMFY_URL}/system_stats" && break
      sleep 1
    done
    if http_ok "${COMFY_URL}/system_stats"; then
      echo "    comfy healthy"
    else
      echo "WARN: Comfy did not become healthy — check ${LOG_DIR}/comfy.log"
    fi
  fi
else
  if http_ok "${COMFY_URL}/system_stats"; then
    echo "  · comfy healthy at ${COMFY_URL}"
  else
    echo "  · comfy not up (mock-only OK). For real gen: ./scripts/nemesis/up.sh --with-comfy"
  fi
fi

# Force mock for this process tree if requested
if [[ "$FORCE_MOCK" -eq 1 ]]; then
  export INSTANTIMPACT_MOCK_GENERATION=true
  export INSTANTIMPACT_COMFY_ENABLED=false
  echo "  · mock generation forced for this session"
fi

export INSTANTIMPACT_REDIS_URL="$REDIS_URL"
export INSTANTIMPACT_COMFY_URL="$COMFY_URL"
export INSTANTIMPACT_COMFY_CKPT_NAME="$COMFY_CKPT"
export INSTANTIMPACT_DATA_DIR="${INSTANTIMPACT_DATA_DIR:-${ROOT}/data}"
export INSTANTIMPACT_WORKFLOWS_DIR="${INSTANTIMPACT_WORKFLOWS_DIR:-${ROOT}/workflows}"
# Resolve relative data/workflows to absolute for worker
if [[ "${INSTANTIMPACT_DATA_DIR}" != /* ]]; then
  export INSTANTIMPACT_DATA_DIR="${ROOT}/${INSTANTIMPACT_DATA_DIR#./}"
fi
if [[ "${INSTANTIMPACT_WORKFLOWS_DIR}" != /* ]]; then
  export INSTANTIMPACT_WORKFLOWS_DIR="${ROOT}/${INSTANTIMPACT_WORKFLOWS_DIR#./}"
fi

# Ensure web deps once
if [[ ! -d "${ROOT}/apps/web/node_modules" ]]; then
  echo "  → npm install (web)"
  (cd "${ROOT}/apps/web" && npm install)
fi

# API
start_bg api \
  bash -c "cd '${ROOT}' && exec '${VENV_PY}' -m uvicorn app.main:app --app-dir apps/api --host '${API_HOST}' --port '${API_PORT}'"

# Worker
start_bg worker \
  bash -c "cd '${ROOT}/apps/worker' && \
    export INSTANTIMPACT_REDIS_URL='${REDIS_URL}' \
           INSTANTIMPACT_COMFY_URL='${COMFY_URL}' \
           INSTANTIMPACT_COMFY_CKPT_NAME='${COMFY_CKPT}' \
           INSTANTIMPACT_DATA_DIR='${INSTANTIMPACT_DATA_DIR}' \
           INSTANTIMPACT_WORKFLOWS_DIR='${INSTANTIMPACT_WORKFLOWS_DIR}' && \
    exec '${VENV_PY}' -m worker.main"

# Web (Vite proxies /api → API)
start_bg web \
  bash -c "cd '${ROOT}/apps/web' && \
    export VITE_API_PROXY='http://127.0.0.1:${API_PORT}' && \
    exec npm run dev -- --host 0.0.0.0 --port '${WEB_PORT}'"

echo ""
echo "== Ready (background) =="
echo "  UI:     http://10.10.101.150:${WEB_PORT}"
echo "  API:    http://10.10.101.150:${API_PORT}/docs"
echo "  logs:   ${LOG_DIR}/"
echo "  pids:   ${PID_DIR}/"
echo ""
echo "  One-terminal control:"
echo "    bash scripts/ii status"
echo "    bash scripts/ii logs          # tail all (Ctrl+C keeps services up)"
echo "    bash scripts/ii logs worker"
echo "    bash scripts/ii stop"
echo ""
echo "  Browser token (once):"
echo "    localStorage.setItem('instantimpact_api_token', '<token from .env>')"
