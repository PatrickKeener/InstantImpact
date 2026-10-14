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

show_proc supervisor
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
loras="${INSTANTIMPACT_COMFY_LORAS_DIR:-}"
if [[ -n "$loras" && -d "$loras" && -w "$loras" ]]; then
  echo "  ✓ loras      ${loras}"
elif [[ -n "$loras" ]]; then
  echo "  ✗ loras      ${loras} (missing or not writable)"
else
  echo "  ✗ loras      INSTANTIMPACT_COMFY_LORAS_DIR is unset"
fi
echo "  · lifecycle  ${INSTANTIMPACT_COMFY_LIFECYCLE:-job}"

echo ""
echo "  logs: ${LOG_DIR}/"
if command -v docker >/dev/null 2>&1; then
  for name in instantimpact-api instantimpact-worker instantimpact-web; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
      echo "  ✗ docker ${name} is running and conflicts with the native stack"
    fi
  done
  pause="${INSTANTIMPACT_GPU_PAUSE_CONTAINERS// /}"
  if [[ -n "$pause" ]]; then
    IFS=',' read -ra gpu_names <<< "$pause"
    for name in "${gpu_names[@]}"; do
      [[ -z "$name" ]] && continue
      state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
      echo "  · gpu ${name}: ${state}"
    done
  fi
fi
