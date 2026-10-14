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
  load_dotenv
  echo "  Edit ${ROOT}/.env and set INSTANTIMPACT_API_TOKEN before using the UI."
fi

if [[ "$STOP_VLLM" -eq 1 ]]; then
  stop_vllm_if_requested
fi

validate_native_config
disable_compose_app_stack
ensure_redis

# Comfy (optional start)
if [[ "$WITH_COMFY" -eq 1 ]]; then
  start_comfy_server || echo "WARN: continuing without healthy Comfy"
else
  if http_ok "${COMFY_URL}/system_stats"; then
    echo "  · comfy healthy at ${COMFY_URL}"
  else
    echo "  · comfy idle — worker starts it per still job, then restores vLLM/Ollama"
  fi
fi

# Force mock for this process tree if requested
if [[ "$FORCE_MOCK" -eq 1 ]]; then
  export INSTANTIMPACT_MOCK_GENERATION=true
  export INSTANTIMPACT_COMFY_ENABLED=false
  echo "  · mock generation forced for this session"
fi

export_runtime_env
start_app_processes

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
