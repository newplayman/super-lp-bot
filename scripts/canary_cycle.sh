#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${LPBOT_CANARY_CONFIG:-configs/config.canary.toml}"
BINARY="${LPBOT_CANARY_BINARY:-./bin/lpbot-live}"
TX_HASH="${LPBOT_CANARY_TX_HASH:-}"
TOKEN_ID="${LPBOT_CANARY_TOKEN_ID:-}"
RUN_EXIT="${LPBOT_CANARY_CYCLE_EXIT:-NO}"

log() {
  printf '[canary-cycle] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

require_confirm() {
  if [[ "${LPBOT_CONFIRM_CANARY_CYCLE:-}" != "YES" ]]; then
    log "blocked: set LPBOT_CONFIRM_CANARY_CYCLE=YES to run"
    exit 2
  fi
}

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then set -a; . ./.env.postgres; set +a; fi
  if [[ -f ./.env.canary ]]; then set -a; . ./.env.canary; set +a; fi
  export POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
}

run_step() {
  local name="$1"
  shift
  log "stage=${name} started"
  "$@"
  log "stage=${name} ok"
}

extract_field() {
  local text="$1"
  local key="$2"
  printf '%s\n' "$text" | tr ' ' '\n' | sed -n "s/^${key}=//p" | tail -1
}

require_confirm
load_env

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  log "blocked: POSTGRES_DSN/DATABASE_URL is empty"
  exit 2
fi

cd "$ROOT_DIR"
run_step preflight "$BINARY" --config="$CONFIG_PATH" --canary-preflight

if [[ -z "$TX_HASH" ]]; then
  log "stage=prepare started"
  LPBOT_CONFIRM_CANARY_PREPARE=YES "$BINARY" --config="$CONFIG_PATH" --canary-prepare
  log "stage=prepare ok"

  log "stage=mint started"
  mint_output="$(LPBOT_CONFIRM_CANARY_MINT=YES "$BINARY" --config="$CONFIG_PATH" --canary-mint 2>&1)" || {
    status=$?
    printf '%s\n' "$mint_output" >&2
    if printf '%s\n' "$mint_output" | grep -q "canary quality gate blocked"; then
      log "stage=mint blocked_by_quality_gate"
      exit 20
    fi
    log "stage=mint failed status=${status}"
    exit "$status"
  }
  printf '%s\n' "$mint_output"
  TX_HASH="$(extract_field "$mint_output" hash)"
  if [[ -z "$TX_HASH" ]]; then
    log "stage=mint failed: could not parse tx hash"
    exit 1
  fi
  log "stage=mint ok tx_hash=${TX_HASH}"
else
  log "stage=mint skipped tx_hash=${TX_HASH}"
fi

if [[ -z "$TOKEN_ID" ]]; then
  log "stage=reconcile_mint started tx_hash=${TX_HASH}"
  reconcile_output="$($BINARY --config="$CONFIG_PATH" --canary-reconcile-mint --tx-hash="$TX_HASH" 2>&1)" || {
    status=$?
    printf '%s\n' "$reconcile_output" >&2
    log "stage=reconcile_mint failed status=${status}"
    exit "$status"
  }
  printf '%s\n' "$reconcile_output"
  TOKEN_ID="$(extract_field "$reconcile_output" token_id)"
  if [[ -z "$TOKEN_ID" ]]; then
    log "stage=reconcile_mint failed: could not parse token_id"
    exit 1
  fi
  log "stage=reconcile_mint ok token_id=${TOKEN_ID}"
else
  log "stage=reconcile_mint skipped token_id=${TOKEN_ID}"
fi

run_step exit_preflight "$BINARY" --config="$CONFIG_PATH" --canary-exit-preflight --token-id="$TOKEN_ID"

if [[ "$RUN_EXIT" == "YES" ]]; then
  log "stage=exit started token_id=${TOKEN_ID}"
  LPBOT_CONFIRM_CANARY_EXIT=YES "$BINARY" --config="$CONFIG_PATH" --canary-exit --token-id="$TOKEN_ID"
  log "stage=exit ok token_id=${TOKEN_ID}"
else
  log "stage=exit skipped: set LPBOT_CANARY_CYCLE_EXIT=YES to broadcast exit"
fi

log "complete tx_hash=${TX_HASH} token_id=${TOKEN_ID} exit=${RUN_EXIT}"
