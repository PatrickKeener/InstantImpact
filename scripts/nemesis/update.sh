#!/usr/bin/env bash
# Update the native stack in place: stop, fast-forward, refresh deps, start, check.
#
# Usage:
#   bash scripts/nemesis/update.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"
load_dotenv

managed=0
if command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet instantimpact 2>/dev/null; then
  managed=1
fi

start_stack() {
  if [[ "$managed" -eq 1 ]]; then
    sudo systemctl start instantimpact
  else
    bash "${ROOT}/scripts/ii" start
  fi
}

echo "== InstantImpact update =="
cd "$ROOT"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: the checkout has local changes. Commit or stash them before updating."
  exit 1
fi

if [[ "$managed" -eq 1 ]]; then
  echo "  → systemctl stop instantimpact"
  sudo systemctl stop instantimpact
else
  bash "${ROOT}/scripts/ii" stop
fi

if ! git pull --ff-only; then
  echo "ERROR: git pull failed. Starting the previous checkout."
  start_stack || true
  exit 1
fi

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: missing ${VENV_PY}"
  exit 1
fi
"$VENV_PIP" install -e ".[dev]"
if [[ -f "${ROOT}/apps/web/package-lock.json" ]]; then
  (cd "${ROOT}/apps/web" && npm install)
fi

start_stack
sleep 2
bash "${ROOT}/scripts/ii" status
if ! http_ok "http://127.0.0.1:${API_PORT}/api/system/health"; then
  echo "ERROR: API did not become healthy on :${API_PORT}. See ${LOG_DIR}/api.log"
  exit 1
fi
echo "Update complete. API is healthy on :${API_PORT}."
