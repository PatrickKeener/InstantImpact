#!/usr/bin/env bash
# Foreground supervisor for systemd. Restarts API, worker, or web if one exits.
# SIGTERM stops the stack, including Comfy, so the worker can restore GPU services.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_dotenv
ensure_run_dirs

finish() {
  trap - EXIT TERM INT
  export II_FROM_SUPERVISOR=1
  bash "${SCRIPT_DIR}/down.sh" --with-comfy || true
  rm -f "${PID_DIR}/supervisor.pid"
}
trap finish EXIT
trap 'exit 0' TERM INT

echo "== InstantImpact supervisor =="
validate_native_config
disable_compose_app_stack
ensure_redis
export_runtime_env
echo $$ >"${PID_DIR}/supervisor.pid"
start_app_processes

while true; do
  for name in api worker web; do
    if ! is_running "$name"; then
      echo "  → ${name} exited; restarting"
      case "$name" in
        api) start_api_process || true ;;
        worker) start_worker_process || true ;;
        web) start_web_process || true ;;
      esac
    fi
  done
  sleep 5 &
  wait $! || true
done
