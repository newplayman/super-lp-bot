#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_SRC="${SCRIPT_DIR}/lpbot-quote-refresh.service"
TMR_SRC="${SCRIPT_DIR}/lpbot-quote-refresh.timer"
DEST_DIR="/etc/systemd/system"

if [[ ! -f "${SVC_SRC}" || ! -f "${TMR_SRC}" ]]; then
  echo "Error: Missing source unit files: ${SVC_SRC} or ${TMR_SRC}" >&2
  exit 1
fi

mkdir -p /var/log/lpbot 2>/dev/null || true

if [[ "${EUID}" -eq 0 ]]; then
  cp -f "${SVC_SRC}" "${DEST_DIR}/"
  cp -f "${TMR_SRC}" "${DEST_DIR}/"
  systemctl daemon-reload
else
  echo "[WARN] Not running as root; skipping copy to ${DEST_DIR} and daemon-reload."
fi

echo "[BLOCKED_BY_OWNER_FREEZE] NOT enabling timer. Run 'systemctl enable --now lpbot-quote-refresh.timer' manually after Owner approval."
exit 0
