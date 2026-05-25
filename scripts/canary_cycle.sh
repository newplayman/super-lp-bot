#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${LPBOT_CANARY_CONFIG:-configs/config.canary.toml}"
BINARY="${LPBOT_CANARY_BINARY:-./bin/lpbot-live}"
TX_HASH="${LPBOT_CANARY_TX_HASH:-}"
TOKEN_ID="${LPBOT_CANARY_TOKEN_ID:-}"
RUN_EXIT="${LPBOT_CANARY_CYCLE_EXIT:-NO}"
RUN_EVIDENCE="${LPBOT_CANARY_RUN_EVIDENCE:-YES}"
PROFITABILITY_GATE="${LPBOT_CANARY_EVIDENCE_GATE:-NO}"
MAX_AVG_NET_ERROR_USD="${LPBOT_CANARY_MAX_AVG_NET_ERROR_USD:-}"
MAX_TOTAL_NET_ERROR_USD="${LPBOT_CANARY_MAX_TOTAL_NET_ERROR_USD:-}"
MAX_MISSING_LEDGER_ROWS="${LPBOT_CANARY_MAX_MISSING_LEDGER_ROWS:-}"
EVIDENCE_WINDOW_HOURS="${LPBOT_CANARY_EVIDENCE_WINDOW_HOURS:-168}"
EVIDENCE_ROW_LIMIT="${LPBOT_CANARY_EVIDENCE_ROW_LIMIT:-50}"
EVIDENCE_POOL_ID="${LPBOT_CANARY_EVIDENCE_POOL_ID:-}"

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

have_psql() {
  command -v psql >/dev/null 2>&1
}

escape_sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

run_profitability_evidence() {
  if [[ "$RUN_EVIDENCE" != "YES" ]]; then
    log "profitability_evidence skipped: set LPBOT_CANARY_RUN_EVIDENCE=YES"
    return 0
  fi

  if ! have_psql; then
    log "profitability_evidence skipped: psql not installed"
    return 0
  fi

  local evidence_args=(
    LPBOT_CANARY_EVIDENCE_WINDOW_HOURS="$EVIDENCE_WINDOW_HOURS"
    LPBOT_CANARY_EVIDENCE_ROW_LIMIT="$EVIDENCE_ROW_LIMIT"
    LPBOT_CANARY_EVIDENCE_CONFIG="$CONFIG_PATH"
  )

  if [[ -n "$EVIDENCE_POOL_ID" ]]; then
    evidence_args+=("LPBOT_CANARY_EVIDENCE_POOL_ID=$EVIDENCE_POOL_ID")
  fi

  log "profitability_evidence started"
  if ! "${evidence_args[@]}" ./scripts/canary_profitability_evidence.sh; then
    log "profitability_evidence failed"
    return 0
  fi

  if [[ "$PROFITABILITY_GATE" == "YES" ]]; then
    enforce_profitability_thresholds
  fi

  log "profitability_evidence completed"
}

enforce_profitability_thresholds() {
  if ! have_psql; then
    log "profitability_gate skipped: psql not installed"
    return 0
  fi

  local window_seconds
  window_seconds=$((EVIDENCE_WINDOW_HOURS * 3600))

  local filter_clause=""
  if [[ -n "$EVIDENCE_POOL_ID" ]]; then
    filter_clause="AND lower(p.pool_id) = lower('$(escape_sql_literal "$EVIDENCE_POOL_ID")')"
  fi

  local query="$(cat <<SQL
WITH target_positions AS (
  SELECT
    p.id,
    COALESCE(p.token_id, '') AS token_id,
    COALESCE(NULLIF(p.amount_usd, ''), '0')::numeric AS principal_usd,
    p.closed_at
  FROM positions p
  WHERE p.status = 'closed'
    AND p.id LIKE 'shadow-canary-live-pos-%'
    AND p.closed_at >= FLOOR(EXTRACT(EPOCH FROM NOW() - (${window_seconds}::bigint * INTERVAL '1 second')))
    ${filter_clause}
),
exit_preflight AS (
  SELECT DISTINCT ON (token_id)
    token_id,
    COALESCE(total_usd::numeric, '0') AS total_usd,
    COALESCE(p.amount_usd::numeric, COALESCE(principal_usd, '0')) AS principal_usd
  FROM canary_exit_preflights p
  ORDER BY token_id, checked_at DESC
),
ledger_rollup AS (
  SELECT
    position_id,
    COALESCE(SUM(amount::numeric), 0) AS realized_net_usd,
    COUNT(*) AS ledger_entry_count
  FROM pnl_ledger
  WHERE position_id LIKE 'shadow-canary-live-pos-%'
  GROUP BY position_id
),
joined AS (
  SELECT
    p.id,
    COALESCE(ep.principal_usd, p.principal_usd) AS preflight_principal_usd,
    COALESCE(ep.total_usd, p.principal_usd) AS preflight_total_usd,
    COALESCE(lr.realized_net_usd, 0) AS realized_net_usd,
    COALESCE(lr.ledger_entry_count, 0) AS ledger_entry_count
  FROM target_positions p
  LEFT JOIN exit_preflight ep ON ep.token_id = p.token_id
  LEFT JOIN ledger_rollup lr ON lr.position_id = p.id
)
SELECT
  COUNT(*) AS closed_positions,
  COALESCE(SUM((preflight_total_usd - preflight_principal_usd)),0) AS expected_sum,
  COALESCE(SUM(realized_net_usd),0) AS realized_sum,
  COALESCE(SUM((preflight_total_usd - preflight_principal_usd) - realized_net_usd),0) AS total_net_error,
  COALESCE(AVG((preflight_total_usd - preflight_principal_usd) - realized_net_usd),0) AS avg_net_error,
  COUNT(*) FILTER (WHERE ledger_entry_count = 0) AS positions_without_ledger_rows
FROM joined;
SQL
)"

  local metrics
  if ! metrics="$(psql "$POSTGRES_DSN" -X -A -F $'\t' -P pager=off -P border=0 -t -c "$query" 2>/tmp/lpbot-canary-cycle-gate.log)"; then
    log "profitability_gate failed: cannot query summary, see /tmp/lpbot-canary-cycle-gate.log"
    cat /tmp/lpbot-canary-cycle-gate.log
    rm -f /tmp/lpbot-canary-cycle-gate.log
    return 0
  fi

  rm -f /tmp/lpbot-canary-cycle-gate.log

  local closed_positions expected_sum realized_sum total_net_error avg_net_error missing_rows
  IFS=$'\t' read -r closed_positions expected_sum realized_sum total_net_error avg_net_error missing_rows <<<"$metrics"

  log "profitability_gate metrics: closed=$closed_positions expected_sum=$expected_sum realized_sum=$realized_sum total_net_error=$total_net_error avg_net_error=$avg_net_error missing_rows=$missing_rows"

  if [[ -n "$MAX_AVG_NET_ERROR_USD" ]]; then
    if awk -v v="$avg_net_error" -v t="$MAX_AVG_NET_ERROR_USD" 'BEGIN { if ((v<0?-v:v) > t) exit 1 }'; then
      :
    else
      log "profitability_gate failed: avg_net_error_usd absolute ${avg_net_error} exceeds limit ${MAX_AVG_NET_ERROR_USD}"
      return 1
    fi
  fi

  if [[ -n "$MAX_TOTAL_NET_ERROR_USD" ]]; then
    if awk -v v="$total_net_error" -v t="$MAX_TOTAL_NET_ERROR_USD" 'BEGIN { if ((v<0?-v:v) > t) exit 1 }'; then
      :
    else
      log "profitability_gate failed: total_net_error_usd absolute ${total_net_error} exceeds limit ${MAX_TOTAL_NET_ERROR_USD}"
      return 1
    fi
  fi

  if [[ -n "$MAX_MISSING_LEDGER_ROWS" ]]; then
    if (( missing_rows > MAX_MISSING_LEDGER_ROWS )); then
      log "profitability_gate failed: positions_without_ledger_rows=${missing_rows} exceeds limit ${MAX_MISSING_LEDGER_ROWS}"
      return 1
    fi
  fi

  return 0
}

print_summary_table() {
  local title="$1"
  local sql="$2"
  log "summary=${title}"
  psql "$POSTGRES_DSN" -X -A -F $'\t' -P pager=off -c "$sql" || log "summary=${title} unavailable"
}

print_canary_summary() {
  if ! have_psql; then
    log "summary skipped: psql not installed"
    return 0
  fi
  print_summary_table "positions" "
    SELECT id, status, COALESCE(token_id,''), pool_id, opened_at, closed_at
    FROM positions
    WHERE id LIKE 'shadow-canary-live-pos-%'
    ORDER BY opened_at DESC
    LIMIT 5;
  "
  print_summary_table "events" "
    SELECT command, stage, status, COALESCE(token_id,''), COALESCE(tx_hash,''), created_at
    FROM canary_events
    ORDER BY created_at DESC
    LIMIT 8;
  "
  print_summary_table "exit_preflights" "
    SELECT token_id, status, COALESCE(decrease_tx_hash,''), COALESCE(collect_tx_hash,''), updated_at
    FROM canary_exit_preflights
    ORDER BY updated_at DESC
    LIMIT 5;
  "
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

print_canary_summary
run_profitability_evidence
log "complete tx_hash=${TX_HASH} token_id=${TOKEN_ID} exit=${RUN_EXIT}"
