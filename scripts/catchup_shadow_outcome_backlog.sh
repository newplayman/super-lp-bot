#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export LPBOT_SHADOW_OBS_CONFIG="${LPBOT_SHADOW_OBS_CONFIG:-configs/config.shadow.research.toml}"
export LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS="${LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS:-900}"
export LPBOT_SHADOW_BACKFILL_LOCK_FILE="${LPBOT_SHADOW_BACKFILL_LOCK_FILE:-/tmp/lpbot_shadow_backfill.lock}"
export LPBOT_SHADOW_BACKFILL_LOCK_WAIT_SECONDS="${LPBOT_SHADOW_BACKFILL_LOCK_WAIT_SECONDS:-5}"

exec "${ROOT_DIR}/scripts/capture_shadow_observation_snapshot.sh"
