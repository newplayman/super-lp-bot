#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_NAME="$(basename "$0")"
RUN_DIR="${ROOT_DIR}/run/audits"
OUTPUT_DEFAULT="${RUN_DIR}/canary-profitability-evidence-$(date -u +%Y%m%d-%H%M%SZ).md"

WINDOW_HOURS="${LPBOT_CANARY_EVIDENCE_WINDOW_HOURS:-168}"
ROW_LIMIT="${LPBOT_CANARY_EVIDENCE_ROW_LIMIT:-50}"
POOL_FILTER="${LPBOT_CANARY_EVIDENCE_POOL_ID:-}"
OUTPUT_FILE="${LPBOT_CANARY_EVIDENCE_OUTPUT:-$OUTPUT_DEFAULT}"
CONFIG_PATH="${LPBOT_CANARY_EVIDENCE_CONFIG:-configs/config.canary.toml}"

WINDOW_SECONDS=$((WINDOW_HOURS * 3600))

escape_sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then
    set -a
    . ./.env.postgres
    set +a
  fi
  if [[ -f ./.env.canary ]]; then
    set -a
    . ./.env.canary
    set +a
  fi
  if [[ -f ./.env.live ]]; then
    set -a
    . ./.env.live
    set +a
  fi

  export POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
}

require_env() {
  if [[ -z "${POSTGRES_DSN:-}" ]]; then
    log "blocked: POSTGRES_DSN / DATABASE_URL is empty"
    exit 2
  fi
  if ! command -v psql >/dev/null 2>&1; then
    log "blocked: psql not installed"
    exit 2
  fi
}

run_query() {
  local title="$1"
  local sql="$2"

  {
    echo
    echo "## ${title}"
    echo
    echo '```'
    psql "$POSTGRES_DSN" \
      -X \
      -A \
      -F $'\t' \
      -P pager=off \
      -P fieldsep=$'\t' \
      -P footer=off \
      -P border=0 \
      -c "$sql"
    echo '```'
  } >> "$OUTPUT_FILE"
}

build_filter_clause() {
  local filter="$1"
  if [[ -z "$filter" ]]; then
    echo ""
  else
    echo "AND lower(p.pool_id) = lower('$(escape_sql_literal "$filter")')"
  fi
}

make_summary_sql() {
  local filter_clause="$1"
  cat <<SQL
WITH target_positions AS (
  SELECT
    p.id,
    COALESCE(p.token_id, '') AS token_id,
    COALESCE(NULLIF(p.amount_usd, ''), '0')::numeric AS principal_usd,
    p.opened_at,
    p.closed_at
  FROM positions p
  WHERE p.status = 'closed'
    AND p.id LIKE 'shadow-canary-live-pos-%'
    AND p.closed_at >= FLOOR(EXTRACT(EPOCH FROM NOW() - (${WINDOW_SECONDS}::bigint * INTERVAL '1 second')))
    ${filter_clause}
),
exit_preflight AS (
  SELECT DISTINCT ON (token_id)
    token_id,
    principal_usd,
    fee_usd,
    total_usd,
    status,
    checked_at,
    COALESCE(decrease_tx_hash, '') AS decrease_tx_hash,
    COALESCE(collect_tx_hash, '') AS collect_tx_hash,
    COALESCE(error_msg, '') AS error_msg
  FROM canary_exit_preflights
  ORDER BY token_id, checked_at DESC
),
ledger_rollup AS (
  SELECT
    position_id,
    COALESCE(SUM(CASE WHEN kind = 'fee' THEN amount::numeric ELSE 0 END), 0) AS fee_usd,
    COALESCE(SUM(CASE WHEN kind = 'il' THEN amount::numeric ELSE 0 END), 0) AS il_usd,
    COALESCE(SUM(CASE WHEN kind = 'swap' THEN amount::numeric ELSE 0 END), 0) AS swap_usd,
    COALESCE(SUM(CASE WHEN kind = 'gas' THEN amount::numeric ELSE 0 END), 0) AS gas_usd,
    COALESCE(SUM(CASE WHEN kind = 'slippage' THEN amount::numeric ELSE 0 END), 0) AS slippage_usd,
    COALESCE(SUM(amount::numeric), 0) AS realized_net_usd,
    COUNT(*) AS ledger_entry_count
  FROM pnl_ledger
  WHERE position_id LIKE 'shadow-canary-live-pos-%'
  GROUP BY position_id
),
joined AS (
  SELECT
    p.id,
    p.principal_usd,
    COALESCE(ep.total_usd::numeric, p.principal_usd) AS expected_total_usd,
    COALESCE(lr.realized_net_usd, 0) AS realized_net_usd,
    COALESCE(ep.status, '') AS preflight_status,
    COALESCE(lr.ledger_entry_count, 0) AS ledger_entry_count
  FROM target_positions p
  LEFT JOIN exit_preflight ep
    ON ep.token_id = p.token_id
  LEFT JOIN ledger_rollup lr
    ON lr.position_id = p.id
)
SELECT
  COUNT(*) AS total_closed_canary_positions,
  COALESCE(SUM(principal_usd), 0) AS total_principal_opened_usd,
  COALESCE(SUM(expected_total_usd - principal_usd), 0) AS total_expected_net_usd,
  COALESCE(SUM(realized_net_usd), 0) AS total_realized_net_usd,
  COALESCE(SUM((expected_total_usd - principal_usd) - realized_net_usd), 0) AS total_net_error_usd,
  COALESCE(AVG(NULLIF(expected_total_usd - principal_usd, 0)), 0) AS avg_expected_net_usd,
  COALESCE(AVG(NULLIF(realized_net_usd, 0)), 0) AS avg_realized_net_usd,
  COALESCE(AVG(realized_net_usd - (expected_total_usd - principal_usd)), 0) AS avg_net_error_usd,
  COUNT(*) FILTER (WHERE COALESCE(ledger_entry_count, 0) = 0) AS positions_without_ledger_rows,
  COUNT(*) FILTER (WHERE preflight_status = '') AS positions_missing_exit_preflight
FROM joined;
SQL
}

make_positions_sql() {
  local filter_clause="$1"
  local order_clause="${2:-}"
  cat <<SQL
WITH target_positions AS (
  SELECT
    p.id,
    COALESCE(p.token_id, '') AS token_id,
    p.pool_id,
    COALESCE(NULLIF(p.amount_usd, ''), '0')::numeric AS principal_usd,
    p.opened_at,
    p.closed_at
  FROM positions p
  WHERE p.status = 'closed'
    AND p.id LIKE 'shadow-canary-live-pos-%'
    AND p.closed_at >= FLOOR(EXTRACT(EPOCH FROM NOW() - (${WINDOW_SECONDS}::bigint * INTERVAL '1 second')))
    ${filter_clause}
),
exit_preflight AS (
  SELECT DISTINCT ON (token_id)
    token_id,
    principal_usd,
    fee_usd,
    total_usd,
    status,
    checked_at,
    COALESCE(decrease_tx_hash, '') AS decrease_tx_hash,
    COALESCE(collect_tx_hash, '') AS collect_tx_hash,
    COALESCE(error_msg, '') AS error_msg
  FROM canary_exit_preflights
  ORDER BY token_id, checked_at DESC
),
ledger_rollup AS (
  SELECT
    position_id,
    COALESCE(SUM(CASE WHEN kind = 'fee' THEN amount::numeric ELSE 0 END), 0) AS fee_usd,
    COALESCE(SUM(CASE WHEN kind = 'il' THEN amount::numeric ELSE 0 END), 0) AS il_usd,
    COALESCE(SUM(CASE WHEN kind = 'swap' THEN amount::numeric ELSE 0 END), 0) AS swap_usd,
    COALESCE(SUM(CASE WHEN kind = 'gas' THEN amount::numeric ELSE 0 END), 0) AS gas_usd,
    COALESCE(SUM(CASE WHEN kind = 'slippage' THEN amount::numeric ELSE 0 END), 0) AS slippage_usd,
    COALESCE(SUM(amount::numeric), 0) AS realized_net_usd,
    COUNT(*) AS ledger_entry_count,
    COALESCE(MAX(block_time), 0) AS last_ledger_ts,
    COALESCE(MIN(block_time), 0) AS first_ledger_ts
  FROM pnl_ledger
  WHERE position_id LIKE 'shadow-canary-live-pos-%'
  GROUP BY position_id
),
recent_event AS (
  SELECT DISTINCT ON (position_id)
    position_id,
    command,
    stage,
    status,
    COALESCE(tx_hash, '') AS tx_hash
  FROM canary_events
  WHERE position_id LIKE 'shadow-canary-live-pos-%'
  ORDER BY position_id, created_at DESC
),
joined AS (
  SELECT
    p.id,
    p.token_id,
    p.pool_id,
    p.principal_usd,
    p.opened_at,
    p.closed_at,
    COALESCE(ep.principal_usd::numeric, p.principal_usd) AS preflight_principal_usd,
    COALESCE(ep.fee_usd::numeric, 0) AS preflight_fee_usd,
    COALESCE(ep.total_usd::numeric, p.principal_usd) AS preflight_total_usd,
    COALESCE(ep.status, '') AS preflight_status,
    to_timestamp(ep.checked_at) AT TIME ZONE 'UTC' AS preflight_checked_at_utc,
    COALESCE(ep.decrease_tx_hash, '') AS decrease_tx_hash,
    COALESCE(ep.collect_tx_hash, '') AS collect_tx_hash,
    COALESCE(ep.error_msg, '') AS preflight_error,
    COALESCE(lr.fee_usd, 0) AS realized_fee_usd,
    COALESCE(lr.il_usd, 0) AS realized_il_usd,
    COALESCE(lr.swap_usd, 0) AS realized_swap_usd,
    COALESCE(lr.gas_usd, 0) AS realized_gas_usd,
    COALESCE(lr.slippage_usd, 0) AS realized_slippage_usd,
    COALESCE(lr.realized_net_usd, 0) AS realized_net_usd,
    COALESCE(lr.ledger_entry_count, 0) AS ledger_entry_count,
    COALESCE(lr.last_ledger_ts, 0) AS last_ledger_ts,
    COALESCE(lr.first_ledger_ts, 0) AS first_ledger_ts,
    COALESCE(re.command, '') AS last_event_command,
    COALESCE(re.stage, '') AS last_event_stage,
    COALESCE(re.status, '') AS last_event_status,
    COALESCE(re.tx_hash, '') AS last_event_tx_hash
  FROM target_positions p
  LEFT JOIN exit_preflight ep
    ON ep.token_id = p.token_id
  LEFT JOIN ledger_rollup lr
    ON lr.position_id = p.id
  LEFT JOIN recent_event re
    ON re.position_id = p.id
)
SELECT
  p.id AS position_id,
  p.token_id,
  p.pool_id,
  to_timestamp(p.opened_at) AT TIME ZONE 'UTC' AS opened_at_utc,
  to_timestamp(p.closed_at) AT TIME ZONE 'UTC' AS closed_at_utc,
  ROUND((p.closed_at - p.opened_at) / 60.0, 2) AS hold_minutes,
  ROUND(p.principal_usd, 6) AS principal_usd,
  ROUND(p.preflight_principal_usd, 6) AS preflight_principal_usd,
  ROUND(p.preflight_fee_usd, 6) AS preflight_fee_usd,
  ROUND(p.preflight_total_usd, 6) AS preflight_total_usd,
  ROUND((p.preflight_total_usd - p.preflight_principal_usd), 6) AS preflight_expected_net_usd,
  ROUND(p.realized_fee_usd, 6) AS realized_fee_usd,
  ROUND(p.realized_il_usd, 6) AS realized_il_usd,
  ROUND(p.realized_swap_usd, 6) AS realized_swap_usd,
  ROUND(p.realized_gas_usd, 6) AS realized_gas_usd,
  ROUND(p.realized_slippage_usd, 6) AS realized_slippage_usd,
  ROUND(p.realized_net_usd, 6) AS realized_net_usd,
  ROUND(p.realized_net_usd - (p.preflight_total_usd - p.preflight_principal_usd), 6) AS net_error_usd,
  p.ledger_entry_count,
  p.preflight_status,
  p.preflight_checked_at_utc,
  p.decrease_tx_hash,
  p.collect_tx_hash,
  p.preflight_error,
  p.last_event_command,
  p.last_event_stage,
  p.last_event_status,
  p.last_event_tx_hash,
  p.ledger_entry_count > 0 AS has_ledger_rows
FROM joined p
ORDER BY ${order_clause}
LIMIT ${ROW_LIMIT};
SQL
}

main() {
  load_env
  require_env

  if [[ ! -f "$CONFIG_PATH" ]]; then
    log "warn: config not found, continuing anyway: $CONFIG_PATH"
  fi

  mkdir -p "$(dirname "$OUTPUT_FILE")"
  {
    echo "# Canary profitability evidence"
    echo
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Config: $CONFIG_PATH"
    echo "Window: last ${WINDOW_HOURS}h"
    echo "Pool filter: ${POOL_FILTER:-<none>}"
    echo "Postgres: $(echo "$POSTGRES_DSN" | sed 's#://[^@]*@#://***:***@#')"
    echo "Output: $OUTPUT_FILE"
    echo
    echo "Note: expected_net_usd = preflight_total_usd - preflight_principal_usd"
    echo "Note: realized_net_usd = SUM(pnl_ledger.amount) by kind (fee/il/swap/gas/slippage)"
    echo
  } > "$OUTPUT_FILE"

  filter_clause="$(build_filter_clause "$POOL_FILTER")"

  summary_sql="$(make_summary_sql "$filter_clause")"
  run_query "Summary (closed canary positions in window)" "$summary_sql"

  positions_sql="$(make_positions_sql "$filter_clause" "ABS((p.realized_net_usd - (p.preflight_total_usd - p.preflight_principal_usd))::numeric) DESC, p.closed_at DESC")"
  run_query "Closed shadow canary positions (worst net error first)" "$positions_sql"

  positions_sql="$(make_positions_sql "$filter_clause" "(p.preflight_checked_at_utc, p.closed_at) DESC NULLS LAST")"
  run_query "Closed shadow canary positions (latest checked)" "$positions_sql"

  log "report generated: $OUTPUT_FILE"
}

main "$@"
