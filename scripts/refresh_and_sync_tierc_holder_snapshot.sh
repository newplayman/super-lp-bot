#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_PATH="${LPBOT_CONFIG_PATH:-$ROOT_DIR/configs/config.shadow.toml}"
SNAPSHOT_PATH="${LPBOT_TIERC_SNAPSHOT_PATH:-$ROOT_DIR/configs/tierc_holder_overrides.json}"

GOTOOLCHAIN=auto go run -tags=shadow ./cmd/lpbot \
  --config "$CONFIG_PATH" \
  --base-tierc-holder-snapshot-refresh \
  --base-tierc-holder-snapshot-path "$SNAPSHOT_PATH"

"$ROOT_DIR/scripts/sync_tierc_holder_snapshot_to_vps.sh" "$SNAPSHOT_PATH"
