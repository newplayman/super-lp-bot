#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${LPBOT_CANARY_CONFIG:-configs/config.canary.toml}"
BINARY="${LPBOT_CANARY_BINARY:-./bin/lpbot-live}"
TOKEN_ID="${LPBOT_CANARY_TOKEN_ID:-}"
RUN_EXIT_PREFLIGHT="${LPBOT_CANARY_RUN_EXIT_PREFLIGHT:-NO}"

log() {
  printf '[canary-readiness] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
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

have_psql() {
  command -v psql >/dev/null 2>&1
}

print_summary_table() {
  local title="$1"
  local sql="$2"
  log "summary=${title}"
  psql "$POSTGRES_DSN" -X -A -F $'\t' -P pager=off -c "$sql" || log "summary=${title} unavailable"
}

print_readiness_summary() {
  if ! have_psql; then
    log "summary skipped: psql not installed"
    return 0
  fi
  print_summary_table "latest_canary_event" "
    SELECT command, stage, status, COALESCE(token_id,''), COALESCE(tx_hash,''), created_at
    FROM canary_events
    ORDER BY created_at DESC
    LIMIT 5;
  "
  print_summary_table "latest_open_positions" "
    SELECT id, status, COALESCE(token_id,''), pool_id, opened_at
    FROM positions
    WHERE id LIKE 'shadow-canary-live-pos-%'
    ORDER BY opened_at DESC
    LIMIT 5;
  "
  if [[ -n "${TOKEN_ID:-}" ]]; then
    print_summary_table "token_exit_preflight" "
      SELECT token_id, status, principal_usd, fee_usd, total_usd, updated_at
      FROM canary_exit_preflights
      WHERE token_id = '${TOKEN_ID}'
      ORDER BY updated_at DESC
      LIMIT 3;
    "
  fi
}

load_env

cd "$ROOT_DIR"

if [[ ! -x "$BINARY" ]]; then
  log "blocked: binary not executable path=${BINARY}"
  exit 2
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  log "blocked: config not found path=${CONFIG_PATH}"
  exit 2
fi

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  log "blocked: POSTGRES_DSN/DATABASE_URL is empty"
  exit 2
fi

run_step preflight "$BINARY" --config="$CONFIG_PATH" --canary-preflight

if [[ "$RUN_EXIT_PREFLIGHT" == "YES" ]]; then
  if [[ -z "$TOKEN_ID" ]]; then
    log "blocked: LPBOT_CANARY_TOKEN_ID is required when LPBOT_CANARY_RUN_EXIT_PREFLIGHT=YES"
    exit 2
  fi
  run_step exit_preflight "$BINARY" --config="$CONFIG_PATH" --canary-exit-preflight --token-id="$TOKEN_ID"
else
  log "stage=exit_preflight skipped: set LPBOT_CANARY_RUN_EXIT_PREFLIGHT=YES and LPBOT_CANARY_TOKEN_ID=<id>"
fi

print_readiness_summary
log "ready next='scripts/canary_cycle.sh' config=${CONFIG_PATH}"
