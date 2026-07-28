#!/usr/bin/env bash
# Show InstantImpact process + dependency status on nemesis.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_dotenv
ensure_run_dirs

echo "== InstantImpact status =="
echo "  root: ${ROOT}"
echo ""

show_proc() {
  local name="$1"
  if is_running "$name"; then
    local pid
    pid="$(cat "${PID_DIR}/${name}.pid")"
    echo "  ✓ ${name}  pid ${pid}"
  else
    echo "  ✗ ${name}  (not running)"
  fi
}

show_proc api
show_proc worker
show_proc web
show_proc comfy

echo ""
if redis_ok; then
  echo "  ✓ redis  (${REDIS_URL})"
else
  echo "  ✗ redis  not reachable"
fi

if http_ok "${COMFY_URL}/system_stats"; then
  echo "  ✓ comfy  ${COMFY_URL}"
else
  echo "  ✗ comfy  not healthy at ${COMFY_URL}"
fi

if http_ok "http://127.0.0.1:${API_PORT}/api/system/health"; then
  echo "  ✓ api health  :${API_PORT}"
else
  echo "  ✗ api health  :${API_PORT}"
fi

if http_ok "http://127.0.0.1:${WEB_PORT}/"; then
  echo "  ✓ web         :${WEB_PORT}"
else
  echo "  ✗ web         :${WEB_PORT}"
fi

echo ""
echo "  logs: ${LOG_DIR}/"
if command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx vllm; then
    echo "  note: docker vllm is RUNNING (may contend for GPU with Flux)"
  fi
fi
