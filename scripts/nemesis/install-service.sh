#!/usr/bin/env bash
# Install the native InstantImpact stack as a boot service.
#
# Usage (on nemesis, from the repo):
#   sudo bash scripts/nemesis/install-service.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run as root: sudo bash scripts/nemesis/install-service.sh"
  exit 1
fi

SERVICE_USER="${INSTANTIMPACT_SERVICE_USER:-pkeener}"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6 || true)"
if [[ -z "$SERVICE_HOME" || ! -d "$SERVICE_HOME" ]]; then
  echo "ERROR: service user ${SERVICE_USER} does not have a home directory."
  exit 1
fi
if ! id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -qx docker; then
  echo "ERROR: ${SERVICE_USER} is not in the docker group."
  echo "  sudo usermod -aG docker ${SERVICE_USER}"
  echo "  Then start a new login session and run this installer again."
  exit 1
fi

echo "  → stopping any stack started by hand"
bash "${ROOT}/scripts/ii" stop || true

echo "  → giving ${SERVICE_USER} ownership of data/ and .run/"
mkdir -p "${ROOT}/data" "${ROOT}/.run"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${ROOT}/data" "${ROOT}/.run"

UNIT=/etc/systemd/system/instantimpact.service
cat >"$UNIT" <<EOF
[Unit]
Description=InstantImpact native stack
After=network-online.target docker.service
Wants=network-online.target docker.service
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${ROOT}
Environment=HOME=${SERVICE_HOME}
ExecStart=/bin/bash ${ROOT}/scripts/nemesis/supervise.sh
Restart=on-failure
RestartSec=5
TimeoutStopSec=90
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable instantimpact.service
echo ""
echo "Installed ${UNIT}"
echo "  start:  sudo systemctl start instantimpact"
echo "  status: bash ${ROOT}/scripts/ii status"
echo "  logs:   bash ${ROOT}/scripts/ii logs"
echo "  stop:   sudo systemctl stop instantimpact"
