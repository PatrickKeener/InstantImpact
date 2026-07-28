#!/usr/bin/env bash
# Stop InstantImpact processes started by up.sh.
#
# Usage:
#   ./scripts/nemesis/down.sh              # api + worker + web
#   ./scripts/nemesis/down.sh --with-comfy # also stop Comfy if we started it
#   ./scripts/nemesis/down.sh --redis      # also stop docker instantimpact-redis
#   ./scripts/nemesis/down.sh --all        # app + comfy + redis container
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

WITH_COMFY=0
WITH_REDIS=0

for arg in "$@"; do
  case "$arg" in
    --with-comfy) WITH_COMFY=1 ;;
    --redis) WITH_REDIS=1 ;;
    --all) WITH_COMFY=1; WITH_REDIS=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

ensure_run_dirs
echo "== InstantImpact down =="

stop_name web
stop_name worker
stop_name api

if [[ "$WITH_COMFY" -eq 1 ]]; then
  stop_name comfy
else
  if is_running comfy; then
    echo "  · comfy still running (use --with-comfy to stop it)"
  fi
fi

if [[ "$WITH_REDIS" -eq 1 ]]; then
  if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' | grep -qx instantimpact-redis; then
      echo "  → docker stop instantimpact-redis"
      docker stop instantimpact-redis >/dev/null
    else
      echo "  · instantimpact-redis container not running"
    fi
  fi
  echo "  note: system redis-server (apt) is left alone — stop manually if you started it that way"
fi

echo ""
echo "Stopped InstantImpact app processes."
echo "  (vLLM / Ollama / system Redis are not touched unless --redis for our docker redis)"
