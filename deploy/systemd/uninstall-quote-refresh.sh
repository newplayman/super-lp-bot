#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="/etc/systemd/system"

if [[ "${EUID}" -eq 0 ]]; then
  systemctl disable --now lpbot-quote-refresh.timer 2>/dev/null || true
  rm -f "${DEST_DIR}/lpbot-quote-refresh.service" "${DEST_DIR}/lpbot-quote-refresh.timer"
  systemctl daemon-reload
else
  echo "[WARN] Not running as root; skipping disable, removal from ${DEST_DIR}, and daemon-reload."
fi

echo "[OK] Quote refresh cron config removed."
exit 0
