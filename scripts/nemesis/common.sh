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
COMFY_DIR="${COMFY_DIR:-${HOME}/ComfyUI}"
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
  nohup "$@" >>"$logfile" 2>&1 &
  echo $! >"$pidfile"
  sleep 0.3
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
    kill "$pid" 2>/dev/null || true
    # graceful wait
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "    force kill ${name}"
      kill -9 "$pid" 2>/dev/null || true
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
