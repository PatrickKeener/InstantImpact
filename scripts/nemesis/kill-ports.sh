#!/usr/bin/env bash
# Best-effort free InstantImpact ports (orphans from manual multi-terminal starts).
set -euo pipefail

# API / Vite / Comfy defaults used on nemesis
PORTS=(8001 5173 8188)

for p in "${PORTS[@]}"; do
  if command -v fuser >/dev/null 2>&1; then
    if fuser "${p}/tcp" >/dev/null 2>&1; then
      echo "  → freeing port ${p}"
      fuser -k "${p}/tcp" >/dev/null 2>&1 || true
    fi
  elif command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -t -iTCP:"${p}" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "${pids}" ]]; then
      echo "  → freeing port ${p} (pids ${pids})"
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
    fi
  fi
done
