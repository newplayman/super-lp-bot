#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_FILE="${1:-$ROOT_DIR/configs/tierc_holder_overrides.json}"
REMOTE_HOST="${LPBOT_VPS_HOST:-lpbot@157.173.123.24}"
REMOTE_KEY="${LPBOT_VPS_KEY:-$HOME/.ssh/lpbot_ed25519}"
REMOTE_PATH="${LPBOT_VPS_PATH:-/opt/lpbot/lp-bot-v3/configs/tierc_holder_overrides.json}"

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "local snapshot not found: $LOCAL_FILE" >&2
  exit 1
fi

scp -i "$REMOTE_KEY" "$LOCAL_FILE" "$REMOTE_HOST:$REMOTE_PATH"
echo "synced $LOCAL_FILE -> $REMOTE_HOST:$REMOTE_PATH"
