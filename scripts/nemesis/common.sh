#!/usr/bin/env bash
# Shared helpers for InstantImpact nemesis start/stop scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="${ROOT}/.run"
LOG_DIR="${RUN_DIR}/logs"
PID_DIR="${RUN_DIR}/pids"

# Defaults (override via environment or .env)
API_HOST="${INSTANTIMPACT_HOST:-0.0.0.0}"
API_PORT="${INSTANTIMPACT_PORT:-8001}"
WEB_PORT="${INSTANTIMPACT_WEB_PORT:-5173}"
REDIS_URL="${INSTANTIMPACT_REDIS_URL:-redis://127.0.0.1:6379/0}"
COMFY_URL="${INSTANTIMPACT_COMFY_URL:-http://127.0.0.1:8188}"
COMFY_CKPT="${INSTANTIMPACT_COMFY_CKPT_NAME:-flux1-dev-fp8.safetensors}"
COMFY_DIR="${COMFY_DIR:-}"
VENV_PY="${ROOT}/.venv/bin/python"
VENV_PIP="${ROOT}/.venv/bin/pip"

load_dotenv() {
  local f="${ROOT}/.env"
  if [[ -f "$f" ]]; then
    # shellcheck disable=SC1090
    set -a
    # Only export simple KEY=VALUE lines (no multi-line)
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// }" ]] && continue
      if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
        export "$line"
      fi
    done < "$f"
    set +a
  fi
  API_HOST="${INSTANTIMPACT_HOST:-$API_HOST}"
  API_PORT="${INSTANTIMPACT_PORT:-$API_PORT}"
  REDIS_URL="${INSTANTIMPACT_REDIS_URL:-$REDIS_URL}"
  COMFY_URL="${INSTANTIMPACT_COMFY_URL:-$COMFY_URL}"
  COMFY_CKPT="${INSTANTIMPACT_COMFY_CKPT_NAME:-$COMFY_CKPT}"
  if [[ -n "${INSTANTIMPACT_COMFY_DIR:-}" ]]; then
    COMFY_DIR="${INSTANTIMPACT_COMFY_DIR}"
  fi
  resolve_comfy_dir || true
}

ensure_run_dirs() {
  mkdir -p "$LOG_DIR" "$PID_DIR" "${ROOT}/data/db"
}

is_running() {
  local name="$1"
  local pidfile="${PID_DIR}/${name}.pid"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    rm -f "$pidfile"
  fi
  return 1
}

start_bg() {
  local name="$1"
  shift
  local pidfile="${PID_DIR}/${name}.pid"
  local logfile="${LOG_DIR}/${name}.log"

  if is_running "$name"; then
    echo "  · ${name} already running (pid $(cat "$pidfile"))"
    return 0
  fi

  echo "  → starting ${name}"
  # setsid: detach from SSH TTY so closing the terminal does not kill children
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$@" >>"$logfile" 2>&1 < /dev/null &
  else
    nohup "$@" >>"$logfile" 2>&1 < /dev/null &
  fi
  echo $! >"$pidfile"
  sleep 0.5
  if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "    pid $(cat "$pidfile")  log ${logfile}"
  else
    echo "    ERROR: ${name} exited immediately — see ${logfile}"
    rm -f "$pidfile"
    return 1
  fi
}

stop_name() {
  local name="$1"
  local pidfile="${PID_DIR}/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "  · ${name} not tracked"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "  → stopping ${name} (pid ${pid})"
    # Kill process group if possible (worker children)
    kill -- "-${pid}" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "    force kill ${name}"
      kill -9 -- "-${pid}" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "  · ${name} not running (stale pidfile)"
  fi
  rm -f "$pidfile"
}

http_ok() {
  local url="$1"
  curl -sf -o /dev/null --connect-timeout 2 "$url" 2>/dev/null
}

redis_ok() {
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli ping 2>/dev/null | grep -q PONG
  else
    # best-effort TCP check
    (echo >/dev/tcp/127.0.0.1/6379) >/dev/null 2>&1
  fi
}

port_listening() {
  local port="$1"
  ss -tln 2>/dev/null | grep -q ":${port} " || ss -tln 2>/dev/null | grep -q ":${port}$"
}

stop_vllm_if_requested() {
  if command -v docker >/dev/null 2>&1; then
    echo "  → docker stop vllm (free GPU)"
    docker stop vllm 2>/dev/null || echo "    (vllm container not running or not named vllm)"
  fi
}

# Native `ii start` and docker compose both want :8001/:5173. The compose API
# also 503s stills: it only sees a stub Comfy tree (loras mount), not the host
# weights. Stop those app containers so the host API/worker/web own the ports.
stop_compose_app_containers() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  local name
  for name in instantimpact-api instantimpact-worker instantimpact-web; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
      echo "  → docker stop ${name} (native ii stack owns API/web/worker)"
      docker stop "$name" >/dev/null 2>&1 || true
    fi
  done
}

# Locate ComfyUI even when the script is run as root (HOME=/root).
resolve_comfy_dir() {
  local candidates=()
  [[ -n "${INSTANTIMPACT_COMFY_DIR:-}" ]] && candidates+=("${INSTANTIMPACT_COMFY_DIR}")
  [[ -n "${COMFY_DIR:-}" ]] && candidates+=("${COMFY_DIR}")
  if [[ -n "${INSTANTIMPACT_COMFY_LORAS_DIR:-}" ]]; then
    # .../ComfyUI/models/loras → .../ComfyUI
    candidates+=("$(dirname "$(dirname "${INSTANTIMPACT_COMFY_LORAS_DIR}")")")
  fi
  candidates+=("${HOME}/ComfyUI")
  candidates+=("/home/pkeener/ComfyUI")
  candidates+=("$(dirname "${ROOT}")/ComfyUI")
  local d
  for d in /home/*/ComfyUI; do
    [[ -e "$d" ]] && candidates+=("$d")
  done
  local c
  for c in "${candidates[@]}"; do
    if [[ -f "${c}/main.py" ]]; then
      COMFY_DIR="$c"
      return 0
    fi
  done
  return 1
}

# Start native ComfyUI only (does not touch API/web/worker). Safe alongside Docker Compose.
start_comfy_server() {
  if http_ok "${COMFY_URL}/system_stats"; then
    echo "  · comfy already healthy at ${COMFY_URL}"
    return 0
  fi
  if ! resolve_comfy_dir; then
    echo "ERROR: ComfyUI not found (ran as HOME=${HOME}, user=$(id -un))."
    echo "  Tried \$HOME/ComfyUI, /home/pkeener/ComfyUI, INSTANTIMPACT_COMFY_LORAS_DIR parent."
    echo "  Fix:  export INSTANTIMPACT_COMFY_DIR=/home/pkeener/ComfyUI"
    echo "    or add INSTANTIMPACT_COMFY_DIR to .env"
    return 1
  fi
  echo "  · COMFY_DIR=${COMFY_DIR}"
  local comfy_py="${COMFY_DIR}/.venv/bin/python"
  if [[ ! -x "$comfy_py" ]]; then
    comfy_py="python3"
  fi
  local run_as=""
  if [[ "$(id -u)" -eq 0 ]] && command -v stat >/dev/null 2>&1; then
    local owner
    owner="$(stat -c %U "${COMFY_DIR}" 2>/dev/null || true)"
    if [[ -n "$owner" && "$owner" != "root" ]]; then
      run_as="$owner"
      echo "  · launching Comfy as ${run_as} (not root)"
    fi
  fi
  if [[ -n "$run_as" ]] && command -v sudo >/dev/null 2>&1; then
    start_bg comfy \
      sudo -u "$run_as" -H bash -c "cd '${COMFY_DIR}' && exec '${comfy_py}' main.py --listen 127.0.0.1 --port 8188"
  else
    start_bg comfy \
      bash -c "cd '${COMFY_DIR}' && exec '${comfy_py}' main.py --listen 127.0.0.1 --port 8188"
  fi
  echo "    waiting for Comfy..."
  local i
  for i in $(seq 1 60); do
    http_ok "${COMFY_URL}/system_stats" && break
    sleep 1
  done
  if http_ok "${COMFY_URL}/system_stats"; then
    echo "    comfy healthy at ${COMFY_URL}"
    return 0
  fi
  echo "ERROR: Comfy did not become healthy — check ${LOG_DIR}/comfy.log"
  return 1
}
