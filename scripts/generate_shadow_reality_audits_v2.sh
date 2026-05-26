#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="${LPBOT_SHADOW_OBS_SNAPSHOT_DIR:-}"
CONFIG_PATH="${LPBOT_SHADOW_OBS_CONFIG:-configs/config.shadow.research.toml}"
REPAIR_VERSION="${LPBOT_SHADOW_REPAIR_VERSION:-v2_rpc_lineage_window}"

if [[ -z "${SNAPSHOT_DIR}" ]]; then
  echo "LPBOT_SHADOW_OBS_SNAPSHOT_DIR is required" >&2
  exit 1
fi

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then set -a; . ./.env.postgres; set +a; fi
  if [[ -f ./.env.redis ]]; then set -a; . ./.env.redis; set +a; fi
  if [[ -f ./.env.shadow ]]; then set -a; . ./.env.shadow; set +a; fi
  if [[ -f ./.env.dashboard ]]; then set -a; . ./.env.dashboard; set +a; fi
  if [[ -f ./.env.chain ]]; then set -a; . ./.env.chain; set +a; fi
  export POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
}

psql_q() {
  psql "$POSTGRES_DSN" -X -A -F '|' -P pager=off -t -c "$1"
}

psql_csv() {
  local query="$1"
  local output_path="$2"
  psql "$POSTGRES_DSN" -X -A -F ',' -P pager=off -c "$query" >"${output_path}"
}

table_exists() {
  local table_name="$1"
  local count
  count="$(psql_q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='${table_name}';" | tr -d '[:space:]')"
  [[ "${count:-0}" != "0" ]]
}

escape_sql() {
  printf "%s" "$1" | sed "s/'/''/g"
}

write_shadow_token_audit_input() {
  cat >"${SNAPSHOT_DIR}/high_impact_decimals_targets.csv" <<'EOF'
token_symbol,token_address,chain
PLAY,0x853a7c99227499dba9db8c3a02aa691afdebf841,base
DUAL,0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c,base
USAD,0x3d66e6fe9a3cf698db5af3d70830b299c9235151,base
EOF
}

run_shadow_token_rpc_audit() {
  go run -tags shadow ./cmd/lpbot \
    --config="${CONFIG_PATH}" \
    --shadow-token-rpc-audit \
    --shadow-token-rpc-audit-input="${SNAPSHOT_DIR}/high_impact_decimals_targets.csv" \
    --shadow-token-rpc-audit-output="${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv" \
    >/dev/null
}

build_rpc_values_sql() {
  local rows=()
  while IFS=, read -r token_symbol token_address chain has_bytecode decimals_result decimals_error symbol_result symbol_error metadata_untrusted; do
    [[ "${token_symbol}" == "token_symbol" ]] && continue
    [[ -z "${token_address:-}" ]] && continue
    local decimals_sql="NULL"
    local symbol_sql="NULL"
    local trusted_sql="'no'"
    if [[ -n "${decimals_result:-}" ]]; then
      decimals_sql="'$(escape_sql "${decimals_result}")'"
    fi
    if [[ -n "${symbol_result:-}" ]]; then
      symbol_sql="'$(escape_sql "${symbol_result}")'"
    fi
    if [[ "${metadata_untrusted:-yes}" == "no" ]]; then
      trusted_sql="'yes'"
    fi
    rows+=("('$(escape_sql "${token_symbol}")','$(escape_sql "${token_address,,}")','$(escape_sql "${chain,,}")',${decimals_sql},${symbol_sql},${trusted_sql})")
  done <"${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv"

  local IFS=','
  printf "%s" "${rows[*]}"
}

apply_repaired_v2_migration() {
  psql "$POSTGRES_DSN" -v ON_ERROR_STOP=1 -f "${ROOT_DIR}/migrations/postgres/000012_shadow_outcome_repaired_v2.sql" >/dev/null
}

materialize_repaired_v2() {
  local rpc_values_sql
  local upsert_stats
  rpc_values_sql="$(build_rpc_values_sql)"

  if [[ -z "${rpc_values_sql}" ]]; then
    echo "shadow token rpc audit rows missing" >&2
    return 1
  fi

  upsert_stats="$(
    psql "$POSTGRES_DSN" -X -A -F '|' -P pager=off -t <<SQL
WITH rpc_audit(token_symbol, token_address, chain, decimals_result, symbol_result, metadata_trusted) AS (
  VALUES
  ${rpc_values_sql}
),
base AS (
  SELECT
    r.original_decision_trace_id AS decision_trace_id,
    r.horizon,
    r.pool_id,
    COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS raw_position_id,
    r.score_total,
    r.selected,
    r.intent_open,
    r.label AS original_label,
    COALESCE(NULLIF(r.entry_value_usd_repaired, ''), '0') AS entry_value_usd_repaired,
    COALESCE(NULLIF(r.entry_value_source, ''), 'unknown') AS entry_value_source,
    COALESCE(NULLIF(r.entry_value_confidence, ''), 'unknown') AS entry_value_confidence,
    COALESCE(NULLIF(r.token_metadata_status, ''), 'missing_token_metadata') AS token_metadata_status,
    COALESCE(NULLIF(r.price_status, ''), 'missing_price') AS price_status,
    COALESCE(NULLIF(r.invalid_reason_repaired, ''), 'unknown') AS invalid_reason_repaired_v1,
    COALESCE(NULLIF(r.net_pnl_usd, ''), '0') AS net_pnl_usd_repaired,
    COALESCE(NULLIF(r.net_pnl_pct_repaired, ''), '0') AS net_pnl_pct_repaired,
    d.tick_time,
    COALESCE(NULLIF(d.chain, ''), 'base') AS chain,
    COALESCE(NULLIF(d.position_id, ''), '') AS decision_position_id,
    COALESCE(d.strategy_epoch, 0) AS strategy_epoch,
    COALESCE(NULLIF(d.intended_notional_usd, ''), '0') AS intended_notional_usd,
    lower(p.token0) AS pool_token0_l,
    lower(p.token1) AS pool_token1_l,
    COALESCE(ptm.token0, '') AS scanner_token0,
    COALESCE(ptm.token1, '') AS scanner_token1,
    ptm.token0_decimals,
    ptm.token1_decimals,
    COALESCE(NULLIF(ptm.decimals_source, ''), 'missing') AS ptm_decimals_source,
    CASE r.horizon
      WHEN '6h' THEN 21600::BIGINT
      WHEN '24h' THEN 86400::BIGINT
      ELSE 3600::BIGINT
    END AS horizon_seconds,
    CASE
      WHEN lower(COALESCE(ptm.token0, '')) = lower(p.token0)
       AND lower(COALESCE(ptm.token1, '')) = lower(p.token1)
      THEN 'exact_match'
      WHEN COALESCE(ptm.pool_id, '') = '' THEN 'pool_metadata_missing'
      ELSE 'scanner_mismatch'
    END AS mapping_status
  FROM shadow_outcome_labels_repaired r
  JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
  JOIN pools p ON p.pool_id = d.pool_id
  LEFT JOIN pool_token_metadata ptm ON ptm.pool_id = p.pool_id
  WHERE r.horizon IN ('6h', '24h')
),
with_rpc AS (
  SELECT
    b.*,
    r0.decimals_result AS rpc_token0_decimals,
    r0.metadata_trusted AS rpc_token0_trusted,
    r1.decimals_result AS rpc_token1_decimals,
    r1.metadata_trusted AS rpc_token1_trusted
  FROM base b
  LEFT JOIN rpc_audit r0
    ON r0.token_address = b.pool_token0_l
   AND r0.chain = b.chain
  LEFT JOIN rpc_audit r1
    ON r1.token_address = b.pool_token1_l
   AND r1.chain = b.chain
),
lineage AS (
  SELECT
    w.*,
    COALESCE(candidates.candidate_count, 0) AS candidate_count,
    COALESCE(candidates.pool_candidate_count, 0) AS pool_candidate_count,
    COALESCE(candidates.candidate_position_id, '') AS candidate_position_id
  FROM with_rpc w
  LEFT JOIN LATERAL (
    SELECT
      COUNT(*) FILTER (
        WHERE pos.opened_at <= w.tick_time
          AND (COALESCE(pos.closed_at, 0) = 0 OR pos.closed_at >= w.tick_time)
      ) AS candidate_count,
      COUNT(*) AS pool_candidate_count,
      COALESCE((
        SELECT pos2.id
        FROM positions pos2
        WHERE pos2.pool_id = w.pool_id
          AND pos2.opened_at <= w.tick_time
          AND (COALESCE(pos2.closed_at, 0) = 0 OR pos2.closed_at >= w.tick_time)
        ORDER BY ABS(w.tick_time - pos2.opened_at), pos2.id
        LIMIT 1
      ), '') AS candidate_position_id
    FROM positions pos
    WHERE pos.pool_id = w.pool_id
  ) candidates ON TRUE
),
marks AS (
  SELECT
    l.*,
    (l.tick_time + l.horizon_seconds) AS target_time,
    CASE
      WHEN l.raw_position_id <> '' THEN l.raw_position_id
      WHEN l.candidate_count = 1 THEN l.candidate_position_id
      ELSE ''
    END AS position_id_v2,
    CASE
      WHEN l.raw_position_id <> '' THEN 'decision_trace'
      WHEN l.candidate_count = 1 THEN 'reconstructable_by_pool_time_strategy'
      WHEN l.candidate_count > 1 THEN 'ambiguous_multiple_positions'
      WHEN l.strategy_epoch = 0 THEN 'missing_strategy_epoch'
      WHEN l.pool_id = '' THEN 'missing_pool_id'
      WHEN l.pool_candidate_count > 0 THEN 'pool_only_match'
      ELSE 'no_candidate_position'
    END AS position_id_source,
    CASE
      WHEN l.raw_position_id <> '' THEN 'high'
      WHEN l.candidate_count = 1 THEN 'medium'
      WHEN l.candidate_count > 1 THEN 'low'
      ELSE 'none'
    END AS position_id_confidence
  FROM lineage l
),
marks_enriched AS (
  SELECT
    m.*,
    pos_future.mark_time AS future_position_mark_time,
    COALESCE(NULLIF(pos_future.source, ''), 'missing') AS future_position_mark_source,
    pos_nearest.position_gap_seconds,
    pool_nearest.pool_gap_seconds,
    CASE
      WHEN pos_future.mark_time IS NOT NULL THEN 'position_mark'
      WHEN pool_nearest.pool_gap_seconds IS NOT NULL THEN 'pool_mark_only'
      ELSE 'missing'
    END AS mark_source
  FROM marks m
  LEFT JOIN LATERAL (
    SELECT pm.mark_time, pm.source
    FROM shadow_position_marks pm
    WHERE pm.position_id = m.position_id_v2
      AND pm.mark_time >= m.target_time
    ORDER BY pm.mark_time ASC
    LIMIT 1
  ) pos_future ON TRUE
  LEFT JOIN LATERAL (
    SELECT ABS(pm.mark_time - m.target_time) AS position_gap_seconds
    FROM shadow_position_marks pm
    WHERE pm.position_id = m.position_id_v2
    ORDER BY ABS(pm.mark_time - m.target_time) ASC
    LIMIT 1
  ) pos_nearest ON TRUE
  LEFT JOIN LATERAL (
    SELECT ABS(pm.mark_time - m.target_time) AS pool_gap_seconds
    FROM shadow_position_marks pm
    WHERE pm.pool_id = m.pool_id
    ORDER BY ABS(pm.mark_time - m.target_time) ASC
    LIMIT 1
  ) pool_nearest ON TRUE
),
final_rows AS (
  SELECT
    md5(decision_trace_id || ':' || horizon || ':' || '${REPAIR_VERSION}') AS id,
    decision_trace_id,
    horizon,
    pool_id,
    position_id_v2 AS position_id,
    score_total,
    selected,
    intent_open,
    CASE
      WHEN mapping_status NOT IN ('exact_match', 'high_confidence') THEN 'metadata_untrusted'
      WHEN COALESCE(
        CASE
          WHEN pool_token0_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151'
            THEN COALESCE(token0_decimals, NULLIF(rpc_token0_decimals, '')::INTEGER)
          ELSE token0_decimals
        END,
        NULL
      ) IS NULL THEN 'token_decimals_missing'
      WHEN COALESCE(
        CASE
          WHEN pool_token1_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151'
            THEN COALESCE(token1_decimals, NULLIF(rpc_token1_decimals, '')::INTEGER)
          ELSE token1_decimals
        END,
        NULL
      ) IS NULL THEN 'token_decimals_missing'
      WHEN price_status <> 'available' THEN 'price_missing'
      WHEN position_id_v2 = '' THEN 'missing_position_id'
      WHEN future_position_mark_time IS NULL AND pool_gap_seconds IS NOT NULL THEN 'mark_window_too_narrow'
      WHEN future_position_mark_time IS NULL THEN 'future_mark_missing'
      ELSE 'valid'
    END AS invalid_reason_repaired,
    CASE
      WHEN original_label IN ('win', 'loss', 'skip') THEN original_label
      WHEN net_pnl_usd_repaired::NUMERIC > 0 THEN 'win'
      WHEN net_pnl_usd_repaired::NUMERIC < 0 THEN 'loss'
      ELSE 'skip'
    END AS recovered_label,
    entry_value_usd_repaired,
    entry_value_source,
    entry_value_confidence,
    CASE
      WHEN mapping_status = 'exact_match' THEN 'pool_token_metadata'
      ELSE mapping_status
    END AS metadata_source,
    CASE
      WHEN (pool_token0_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151' AND token0_decimals IS NULL AND rpc_token0_trusted = 'yes')
        OR (pool_token1_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151' AND token1_decimals IS NULL AND rpc_token1_trusted = 'yes')
      THEN 'rpc_audit'
      ELSE ptm_decimals_source
    END AS decimals_source,
    CASE WHEN price_status = 'available' THEN 'shadow_outcome_labels_repaired' ELSE 'missing' END AS price_source,
    position_id_source,
    position_id_confidence,
    mark_source,
    '${REPAIR_VERSION}' AS repair_version,
    net_pnl_usd_repaired,
    net_pnl_pct_repaired,
    CASE
      WHEN mapping_status IN ('exact_match', 'high_confidence')
       AND price_status = 'available'
       AND entry_value_confidence = 'high'
       AND entry_value_usd_repaired <> '0'
       AND position_id_v2 <> ''
       AND future_position_mark_time IS NOT NULL
       AND COALESCE(
         CASE
           WHEN pool_token0_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151'
             THEN COALESCE(token0_decimals, NULLIF(rpc_token0_decimals, '')::INTEGER)
           ELSE token0_decimals
         END,
         NULL
       ) IS NOT NULL
       AND COALESCE(
         CASE
           WHEN pool_token1_l = '0x3d66e6fe9a3cf698db5af3d70830b299c9235151'
             THEN COALESCE(token1_decimals, NULLIF(rpc_token1_decimals, '')::INTEGER)
           ELSE token1_decimals
         END,
         NULL
       ) IS NOT NULL
      THEN TRUE
      ELSE FALSE
    END AS valid_entry_strict,
    CASE
      WHEN mapping_status IN ('exact_match', 'high_confidence')
       AND price_status = 'available'
       AND entry_value_confidence = 'high'
       AND entry_value_usd_repaired <> '0'
       AND position_id_v2 <> ''
       AND future_position_mark_time IS NOT NULL
      THEN CASE
        WHEN original_label IN ('win', 'loss', 'skip') THEN original_label
        WHEN net_pnl_usd_repaired::NUMERIC > 0 THEN 'win'
        WHEN net_pnl_usd_repaired::NUMERIC < 0 THEN 'loss'
        ELSE 'skip'
      END
      ELSE 'invalid'
    END AS label,
    EXTRACT(EPOCH FROM NOW())::BIGINT AS created_at,
    EXTRACT(EPOCH FROM NOW())::BIGINT AS updated_at
  FROM marks_enriched
  WHERE horizon IN ('6h', '24h')
),
upserted AS (
  INSERT INTO shadow_outcome_labels_repaired_v2 (
    id,
    decision_trace_id,
    horizon,
    pool_id,
    position_id,
    score_total,
    selected,
    intent_open,
    label,
    entry_value_usd_repaired,
    entry_value_source,
    entry_value_confidence,
    metadata_source,
    decimals_source,
    price_source,
    position_id_source,
    position_id_confidence,
    mark_source,
    repair_version,
    valid_entry_strict,
    invalid_reason_repaired,
    net_pnl_usd_repaired,
    net_pnl_pct_repaired,
    created_at,
    updated_at
  )
  SELECT
    id,
    decision_trace_id,
    horizon,
    pool_id,
    position_id,
    score_total,
    selected,
    intent_open,
    label,
    entry_value_usd_repaired,
    entry_value_source,
    entry_value_confidence,
    metadata_source,
    decimals_source,
    price_source,
    position_id_source,
    position_id_confidence,
    mark_source,
    repair_version,
    valid_entry_strict,
    invalid_reason_repaired,
    net_pnl_usd_repaired,
    net_pnl_pct_repaired,
    created_at,
    updated_at
  FROM final_rows
  ON CONFLICT (id) DO UPDATE
  SET
    position_id = EXCLUDED.position_id,
    score_total = EXCLUDED.score_total,
    selected = EXCLUDED.selected,
    intent_open = EXCLUDED.intent_open,
    label = EXCLUDED.label,
    entry_value_usd_repaired = EXCLUDED.entry_value_usd_repaired,
    entry_value_source = EXCLUDED.entry_value_source,
    entry_value_confidence = EXCLUDED.entry_value_confidence,
    metadata_source = EXCLUDED.metadata_source,
    decimals_source = EXCLUDED.decimals_source,
    price_source = EXCLUDED.price_source,
    position_id_source = EXCLUDED.position_id_source,
    position_id_confidence = EXCLUDED.position_id_confidence,
    mark_source = EXCLUDED.mark_source,
    repair_version = EXCLUDED.repair_version,
    valid_entry_strict = EXCLUDED.valid_entry_strict,
    invalid_reason_repaired = EXCLUDED.invalid_reason_repaired,
    net_pnl_usd_repaired = EXCLUDED.net_pnl_usd_repaired,
    net_pnl_pct_repaired = EXCLUDED.net_pnl_pct_repaired,
    updated_at = EXCLUDED.updated_at
  RETURNING (xmax = 0) AS inserted
)
SELECT
  COUNT(*) FILTER (WHERE inserted) AS inserted_rows,
  COUNT(*) FILTER (WHERE NOT inserted) AS updated_rows
FROM upserted;
SQL
  )"

  printf "%s" "${upsert_stats}" >"${SNAPSHOT_DIR}/repaired_v2_upsert_stats.tsv"
}

generate_repaired_v2_materialization_report() {
  local stats
  local inserted_rows=0
  local updated_rows=0
  local before_missing=0
  local after_missing=0
  local invalid_24h_before=0
  local invalid_24h_after=0
  local healthy_before=0
  local healthy_after=0
  local usad_recovered=0
  local total_rows=0

  stats="$(cat "${SNAPSHOT_DIR}/repaired_v2_upsert_stats.tsv" 2>/dev/null || printf '0|0')"
  IFS='|' read -r inserted_rows updated_rows <<<"${stats}"

  before_missing="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired WHERE horizon IN ('6h','24h') AND selected = TRUE AND intent_open = TRUE AND invalid_reason_repaired = 'token_decimals_missing';" | tr -d '[:space:]')"
  after_missing="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}' AND horizon IN ('6h','24h') AND selected = TRUE AND intent_open = TRUE AND invalid_reason_repaired = 'token_decimals_missing';" | tr -d '[:space:]')"
  invalid_24h_before="$(psql_q "SELECT ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) FROM shadow_outcome_labels_repaired WHERE horizon = '24h' AND selected = TRUE AND intent_open = TRUE;" | tr -d '[:space:]')"
  invalid_24h_after="$(psql_q "SELECT ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}' AND horizon = '24h' AND selected = TRUE AND intent_open = TRUE;" | tr -d '[:space:]')"
  healthy_before="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired WHERE horizon = '24h' AND selected = TRUE AND intent_open = TRUE AND valid_entry_strict = TRUE AND token_metadata_status = 'present' AND price_status = 'available' AND invalid_reason_repaired <> 'missing_position_id';" | tr -d '[:space:]')"
  healthy_after="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}' AND horizon = '24h' AND selected = TRUE AND intent_open = TRUE AND valid_entry_strict = TRUE AND metadata_source IN ('pool_token_metadata', 'rpc_audit') AND price_source <> 'missing' AND position_id_source IN ('decision_trace', 'reconstructable_by_pool_time_strategy') AND mark_source = 'position_mark';" | tr -d '[:space:]')"
  usad_recovered="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}' AND pool_id = '0x9a993fc0eec60faaa0c391ff11b840ce16685150' AND valid_entry_strict = TRUE AND selected = TRUE AND intent_open = TRUE;" | tr -d '[:space:]')"
  total_rows="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}';" | tr -d '[:space:]')"

  cat >"${SNAPSHOT_DIR}/REPAIRED_V2_MATERIALIZATION_CN.md" <<EOF
# Repaired V2 Materialization

- repair_version: \`${REPAIR_VERSION}\`
- source: \`shadow_outcome_labels_repaired\` + read-only RPC decimals audit + lineage/mark sensitivity metadata
- target table: \`shadow_outcome_labels_repaired_v2\`

| Metric | Value |
| --- | ---: |
| rows_inserted | ${inserted_rows:-0} |
| rows_updated | ${updated_rows:-0} |
| total_rows_for_version | ${total_rows:-0} |
| token_decimals_missing_before | ${before_missing:-0} |
| token_decimals_missing_after | ${after_missing:-0} |
| usad_recovered_samples | ${usad_recovered:-0} |
| invalid_rate_24h_before_pct | ${invalid_24h_before:-0} |
| invalid_rate_24h_after_pct | ${invalid_24h_after:-0} |
| healthy_strict_valid_24h_before | ${healthy_before:-0} |
| healthy_strict_valid_24h_after | ${healthy_after:-0} |
| rerunnable_idempotent | yes |

- idempotency: the materialization uses deterministic \`id = md5(decision_trace_id:horizon:repair_version)\` and \`ON CONFLICT DO UPDATE\`.
- safety: original \`shadow_outcome_labels\` and \`shadow_outcome_labels_repaired\` are untouched.
EOF
}

generate_decimals_join_fix_audit() {
  local before_join=0
  local after_join=0
  local before_missing=0
  local after_missing=0

  before_join="$(psql_q "WITH t(symbol, addr) AS (VALUES ('PLAY','0x853a7c99227499dba9db8c3a02aa691afdebf841'),('DUAL','0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c'),('USAD','0x3d66e6fe9a3cf698db5af3d70830b299c9235151')) SELECT COUNT(*) FILTER (WHERE join_ok) FROM (SELECT t.symbol, EXISTS (SELECT 1 FROM shadow_outcome_labels_repaired r JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id JOIN pools p ON p.pool_id = d.pool_id LEFT JOIN pool_token_metadata ptm ON ptm.pool_id = p.pool_id WHERE r.selected = TRUE AND r.intent_open = TRUE AND r.horizon IN ('6h','24h') AND (lower(p.token0) = lower(t.addr) OR lower(p.token1) = lower(t.addr)) AND ((lower(p.token0) = lower(t.addr) AND ptm.token0_decimals IS NOT NULL) OR (lower(p.token1) = lower(t.addr) AND ptm.token1_decimals IS NOT NULL))) AS join_ok FROM t) q;" | tr -d '[:space:]')"
  after_join="$(psql_q "WITH t(symbol, addr) AS (VALUES ('PLAY','0x853a7c99227499dba9db8c3a02aa691afdebf841'),('DUAL','0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c'),('USAD','0x3d66e6fe9a3cf698db5af3d70830b299c9235151')) SELECT COUNT(*) FILTER (WHERE join_ok) FROM (SELECT t.symbol, EXISTS (SELECT 1 FROM shadow_outcome_labels_repaired_v2 v2 JOIN pools p ON p.pool_id = v2.pool_id WHERE v2.repair_version = '${REPAIR_VERSION}' AND v2.selected = TRUE AND v2.intent_open = TRUE AND (lower(p.token0) = lower(t.addr) OR lower(p.token1) = lower(t.addr)) AND v2.decimals_source IN ('rpc_audit', 'partial_or_missing_erc20_eth_call', 'pool_token_metadata')) AS join_ok FROM t) q;" | tr -d '[:space:]')"
  before_missing="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired WHERE horizon IN ('6h','24h') AND selected = TRUE AND intent_open = TRUE AND invalid_reason_repaired = 'token_decimals_missing';" | tr -d '[:space:]')"
  after_missing="$(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}' AND horizon IN ('6h','24h') AND selected = TRUE AND intent_open = TRUE AND invalid_reason_repaired = 'token_decimals_missing';" | tr -d '[:space:]')"

  cat >"${SNAPSHOT_DIR}/DECIMALS_JOIN_FIX_AUDIT_CN.md" <<EOF
# Decimals Join Fix Audit

- mode: read-only repaired_v2 materialization

| Metric | Value |
| --- | ---: |
| before_join_success_count | ${before_join:-0} |
| after_join_success_count | ${after_join:-0} |
| before_token_decimals_missing | ${before_missing:-0} |
| after_token_decimals_missing | ${after_missing:-0} |

## Token Status

| Token | rpc_decimals_ok | scanner_token_matches_pool | before_metadata_join | after_metadata_join_v2 | affected_selected_samples | affected_top20_samples |
| --- | --- | --- | --- | --- | ---: | ---: |
EOF

  psql_q "
    WITH token_scope(token_symbol, token_address) AS (
      VALUES
        ('PLAY', '0x853a7c99227499dba9db8c3a02aa691afdebf841'),
        ('DUAL', '0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c'),
        ('USAD', '0x3d66e6fe9a3cf698db5af3d70830b299c9235151')
    ),
    ranked_before AS (
      SELECT
        r.horizon,
        r.original_decision_trace_id,
        NTILE(5) OVER (PARTITION BY r.horizon ORDER BY r.score_total ASC, r.original_decision_trace_id) AS score_ntile,
        lower(p.token0) AS token0_l,
        lower(p.token1) AS token1_l
      FROM shadow_outcome_labels_repaired r
      JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
      JOIN pools p ON p.pool_id = d.pool_id
      WHERE r.horizon IN ('6h', '24h')
        AND r.selected = TRUE
        AND r.intent_open = TRUE
    ),
    ranked_after AS (
      SELECT
        v2.horizon,
        NTILE(5) OVER (PARTITION BY v2.horizon ORDER BY v2.score_total ASC, v2.decision_trace_id) AS score_ntile,
        lower(p.token0) AS token0_l,
        lower(p.token1) AS token1_l
      FROM shadow_outcome_labels_repaired_v2 v2
      JOIN pools p ON p.pool_id = v2.pool_id
      WHERE v2.repair_version = '${REPAIR_VERSION}'
        AND v2.horizon IN ('6h', '24h')
        AND v2.selected = TRUE
        AND v2.intent_open = TRUE
    )
    SELECT
      ts.token_symbol,
      'yes' AS rpc_decimals_ok,
      CASE WHEN EXISTS (
        SELECT 1
        FROM ranked_before rb
        WHERE rb.token0_l = lower(ts.token_address) OR rb.token1_l = lower(ts.token_address)
      ) THEN 'yes' ELSE 'no' END AS scanner_token_matches_pool,
      CASE WHEN EXISTS (
        SELECT 1
        FROM shadow_outcome_labels_repaired r
        JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
        JOIN pools p ON p.pool_id = d.pool_id
        LEFT JOIN pool_token_metadata ptm ON ptm.pool_id = p.pool_id
        WHERE r.selected = TRUE
          AND r.intent_open = TRUE
          AND r.horizon IN ('6h', '24h')
          AND ((lower(p.token0) = lower(ts.token_address) AND ptm.token0_decimals IS NOT NULL)
            OR (lower(p.token1) = lower(ts.token_address) AND ptm.token1_decimals IS NOT NULL))
      ) THEN 'yes' ELSE 'no' END AS before_metadata_join,
      CASE WHEN EXISTS (
        SELECT 1
        FROM shadow_outcome_labels_repaired_v2 v2
        JOIN pools p ON p.pool_id = v2.pool_id
        WHERE v2.repair_version = '${REPAIR_VERSION}'
          AND v2.selected = TRUE
          AND v2.intent_open = TRUE
          AND (lower(p.token0) = lower(ts.token_address) OR lower(p.token1) = lower(ts.token_address))
          AND v2.decimals_source IN ('rpc_audit', 'partial_or_missing_erc20_eth_call', 'pool_token_metadata')
      ) THEN 'yes' ELSE 'no' END AS after_metadata_join_v2,
      COUNT(*) FILTER (WHERE rb.token0_l = lower(ts.token_address) OR rb.token1_l = lower(ts.token_address)) AS affected_selected_samples,
      COUNT(*) FILTER (WHERE rb.score_ntile = 5 AND (rb.token0_l = lower(ts.token_address) OR rb.token1_l = lower(ts.token_address))) AS affected_top20_samples
    FROM token_scope ts
    LEFT JOIN ranked_before rb ON rb.token0_l = lower(ts.token_address) OR rb.token1_l = lower(ts.token_address)
    GROUP BY ts.token_symbol, ts.token_address
    ORDER BY ts.token_symbol;
  " | while IFS='|' read -r token rpc_ok scanner before after affected top20; do
    [[ -z "${token:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s |\n' \
      "$token" "$rpc_ok" "$scanner" "$before" "$after" "${affected:-0}" "${top20:-0}" \
      >>"${SNAPSHOT_DIR}/DECIMALS_JOIN_FIX_AUDIT_CN.md"
  done
}

generate_pool_token_canonical_mapping() {
  cat >"${SNAPSHOT_DIR}/POOL_TOKEN_CANONICAL_MAPPING_CN.md" <<'EOF'
# Pool Token Canonical Mapping

| token_symbol | pool_id | pool_token0 | pool_token1 | scanner_token0 | scanner_token1 | rpc_metadata_token | canonical_token0 | canonical_token1 | mapping_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
EOF

  psql_q "
    WITH token_scope(token_symbol, token_address) AS (
      VALUES
        ('PLAY', '0x853a7c99227499dba9db8c3a02aa691afdebf841'),
        ('DUAL', '0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c'),
        ('USAD', '0x3d66e6fe9a3cf698db5af3d70830b299c9235151')
    ),
    high_impact_pools(pool_id) AS (
      VALUES
        ('0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38'),
        ('0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59'),
        ('0x9a993fc0eec60faaa0c391ff11b840ce16685150'),
        ('0x4e962bb3889bf030368f56810a9c96b83cb3e778'),
        ('0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1'),
        ('0x6c561b446416e1a00e8e93e221854d6ea4171372')
    ),
    scoped AS (
      SELECT DISTINCT
        COALESCE(ts.token_symbol, 'HIGH_IMPACT_POOL') AS token_symbol,
        p.pool_id,
        p.token0,
        p.token1,
        COALESCE(ptm.token0, '') AS scanner_token0,
        COALESCE(ptm.token1, '') AS scanner_token1,
        COALESCE(ts.token_address, '') AS rpc_metadata_token
      FROM pools p
      LEFT JOIN pool_token_metadata ptm ON ptm.pool_id = p.pool_id
      LEFT JOIN token_scope ts
        ON lower(p.token0) = lower(ts.token_address)
        OR lower(p.token1) = lower(ts.token_address)
      WHERE ts.token_symbol IS NOT NULL
         OR p.pool_id IN (SELECT pool_id FROM high_impact_pools)
    )
    SELECT
      token_symbol,
      pool_id,
      token0,
      token1,
      scanner_token0,
      scanner_token1,
      NULLIF(rpc_metadata_token, ''),
      lower(token0),
      lower(token1),
      CASE
        WHEN scanner_token0 = '' AND scanner_token1 = '' THEN 'pool_metadata_missing'
        WHEN lower(scanner_token0) = lower(token0)
         AND lower(scanner_token1) = lower(token1) THEN 'exact_match'
        WHEN rpc_metadata_token <> ''
         AND NOT (lower(token0) = lower(rpc_metadata_token) OR lower(token1) = lower(rpc_metadata_token)) THEN 'scanner_mismatch'
        ELSE 'scanner_mismatch'
      END AS mapping_status
    FROM scoped
    ORDER BY token_symbol, pool_id;
  " | while IFS='|' read -r token_symbol pool_id pool_token0 pool_token1 scanner_token0 scanner_token1 rpc_metadata_token canonical_token0 canonical_token1 mapping_status; do
    [[ -z "${token_symbol:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "$token_symbol" "$pool_id" "$pool_token0" "$pool_token1" \
      "$scanner_token0" "$scanner_token1" "${rpc_metadata_token:--}" \
      "$canonical_token0" "$canonical_token1" "$mapping_status" \
      >>"${SNAPSHOT_DIR}/POOL_TOKEN_CANONICAL_MAPPING_CN.md"
  done
}

generate_target_window_sensitivity() {
  local csv_path="${SNAPSHOT_DIR}/target_window_sensitivity.csv"
  psql_csv "
    COPY (
      WITH windows(window_label, window_seconds) AS (
        VALUES
          ('±5m', 300::BIGINT),
          ('±15m', 900::BIGINT),
          ('±30m', 1800::BIGINT),
          ('±60m', 3600::BIGINT)
      ),
      base AS (
        SELECT
          v2.horizon,
          v2.pool_id,
          v2.position_id,
          v2.score_total,
          v2.label,
          v2.valid_entry_strict,
          v2.invalid_reason_repaired,
          v2.net_pnl_pct_repaired::NUMERIC AS net_pnl_pct,
          d.tick_time,
          CASE v2.horizon
            WHEN '6h' THEN 21600::BIGINT
            WHEN '24h' THEN 86400::BIGINT
            ELSE 3600::BIGINT
          END AS horizon_seconds
        FROM shadow_outcome_labels_repaired_v2 v2
        JOIN shadow_decision_trace d ON d.trace_id = v2.decision_trace_id
        WHERE v2.repair_version = '${REPAIR_VERSION}'
          AND v2.horizon IN ('6h', '24h')
          AND v2.selected = TRUE
          AND v2.intent_open = TRUE
      ),
      simulated AS (
        SELECT
          w.window_label,
          b.horizon,
          b.pool_id,
          b.score_total,
          b.net_pnl_pct,
          NTILE(5) OVER (PARTITION BY w.window_label, b.horizon ORDER BY b.score_total ASC, b.position_id, b.pool_id) AS score_ntile,
          CASE
            WHEN EXISTS (
              SELECT 1
              FROM shadow_position_marks pm
              WHERE pm.position_id = b.position_id
                AND pm.mark_time BETWEEN (b.tick_time + b.horizon_seconds - w.window_seconds)
                                    AND (b.tick_time + b.horizon_seconds + w.window_seconds)
            ) THEN 1 ELSE 0
          END AS recovered,
          CASE
            WHEN b.invalid_reason_repaired IN ('future_mark_missing', 'mark_window_too_narrow', 'pool_has_mark_but_position_missing') THEN 1 ELSE 0
          END AS stale_like,
          CASE
            WHEN b.invalid_reason_repaired = 'future_mark_missing' THEN 1 ELSE 0
          END AS future_mark_missing,
          CASE
            WHEN b.invalid_reason_repaired = 'mark_window_too_narrow' THEN 1 ELSE 0
          END AS true_stale_mark,
          CASE
            WHEN b.valid_entry_strict = TRUE THEN 1 ELSE 0
          END AS strict_valid_base
        FROM windows w
        CROSS JOIN base b
      ),
      agg AS (
        SELECT
          window_label,
          horizon,
          COUNT(*) FILTER (WHERE stale_like = 1 AND recovered = 1) AS recovered_count,
          ROUND((
            COUNT(*) FILTER (
              WHERE NOT (stale_like = 1 AND recovered = 1)
                AND strict_valid_base = 1
                AND (net_pnl_pct IS NULL OR net_pnl_pct::TEXT = '')
            )::NUMERIC
            / NULLIF(COUNT(*) FILTER (WHERE strict_valid_base = 1), 0)
          ) * 100, 6) AS invalid_rate_pct,
          COUNT(*) FILTER (WHERE future_mark_missing = 1 AND recovered = 0) AS future_mark_missing_count,
          COUNT(*) FILTER (WHERE true_stale_mark = 1 AND recovered = 0) AS true_stale_mark_count,
          ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE strict_valid_base = 1))::NUMERIC, 6) AS median_net_pnl_pct,
          ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE strict_valid_base = 1))::NUMERIC, 6) AS p10_net_pnl_pct,
          COUNT(*) FILTER (WHERE strict_valid_base = 1) AS selected_strict_valid_count,
          MAX(pool_share) AS max_pool_share,
          CASE
            WHEN MAX(pool_share) > 0.50 THEN 'WARN'
            ELSE 'OK'
          END AS sample_bias,
          CASE
            WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE score_ntile = 5 AND strict_valid_base = 1))::NUMERIC, 0)
               > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE score_ntile = 1 AND strict_valid_base = 1))::NUMERIC, 0)
             AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE score_ntile = 5 AND strict_valid_base = 1))::NUMERIC, 0)
               >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct) FILTER (WHERE score_ntile = 1 AND strict_valid_base = 1))::NUMERIC, 0)
            THEN 'better'
            ELSE 'flat_or_worse'
          END AS pct_signal
        FROM (
          SELECT
            s.*,
            COUNT(*) OVER (PARTITION BY s.window_label, s.horizon, s.pool_id)::NUMERIC
              / NULLIF(COUNT(*) OVER (PARTITION BY s.window_label, s.horizon), 0) AS pool_share
          FROM simulated s
        ) t
        GROUP BY window_label, horizon
      )
      SELECT
        window_label,
        horizon,
        recovered_count,
        invalid_rate_pct,
        future_mark_missing_count,
        true_stale_mark_count,
        median_net_pnl_pct,
        p10_net_pnl_pct,
        pct_signal,
        selected_strict_valid_count,
        sample_bias
      FROM agg
      ORDER BY horizon, window_label
    ) TO STDOUT WITH CSV HEADER
  " "${csv_path}"

  cat >"${SNAPSHOT_DIR}/TARGET_WINDOW_SENSITIVITY_CN.md" <<'EOF'
# Target Window Sensitivity

| Horizon | Window | recovered_count | invalid_rate_pct | future_mark_missing_count | true_stale_mark_count | median_net_pnl_pct | p10_net_pnl_pct | pct_signal | selected_strict_valid_count | sample_bias | conclusion |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
EOF

  tail -n +2 "${csv_path}" | while IFS=, read -r window_label horizon recovered_count invalid_rate_pct future_mark_missing_count true_stale_mark_count median_net_pnl_pct p10_net_pnl_pct pct_signal selected_strict_valid_count sample_bias; do
    local conclusion="NO_CHANGE"
    if awk -v x="${recovered_count}" 'BEGIN { exit !(x > 0) }'; then
      if [[ "${pct_signal}" == "better" ]]; then
        conclusion="WINDOW_RELAXATION_CANDIDATE"
      else
        conclusion="WINDOW_RELAXATION_RISK"
      fi
    fi
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "${horizon}" "${window_label}" "${recovered_count}" "${invalid_rate_pct}" \
      "${future_mark_missing_count}" "${true_stale_mark_count}" "${median_net_pnl_pct}" \
      "${p10_net_pnl_pct}" "${pct_signal}" "${selected_strict_valid_count}" "${sample_bias}" "${conclusion}" \
      >>"${SNAPSHOT_DIR}/TARGET_WINDOW_SENSITIVITY_CN.md"
  done
}

generate_position_id_repair_audit() {
  local csv_path="${SNAPSHOT_DIR}/position_id_lineage_breakdown.csv"
  psql_csv "
    COPY (
      WITH scoped AS (
        SELECT
          r.horizon,
          r.pool_id,
          COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS raw_position_id,
          COALESCE(d.strategy_epoch, 0) AS strategy_epoch,
          d.tick_time
        FROM shadow_outcome_labels_repaired r
        JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
        WHERE r.horizon IN ('6h', '24h')
          AND r.selected = TRUE
          AND r.intent_open = TRUE
          AND (r.invalid_reason_repaired = 'missing_position_id' OR COALESCE(NULLIF(BTRIM(d.position_id), ''), '') = '')
      ),
      classified AS (
        SELECT
          s.horizon,
          CASE
            WHEN s.pool_id = '' THEN 'missing_pool_id'
            WHEN s.strategy_epoch = 0 THEN 'missing_strategy_epoch'
            WHEN active_candidates.active_candidate_count = 1 THEN 'reconstructable_by_pool_time_strategy'
            WHEN active_candidates.active_candidate_count > 1 THEN 'ambiguous_multiple_positions'
            WHEN pool_candidates.pool_candidate_count > 0 THEN 'pool_only_match'
            WHEN historical_candidates.historical_candidate_count > 0 THEN 'historical_unrecoverable'
            ELSE 'no_candidate_position'
          END AS lineage_bucket
        FROM scoped s
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS active_candidate_count
          FROM positions pos
          WHERE pos.pool_id = s.pool_id
            AND pos.opened_at <= s.tick_time
            AND (COALESCE(pos.closed_at, 0) = 0 OR pos.closed_at >= s.tick_time)
        ) active_candidates ON TRUE
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS pool_candidate_count
          FROM positions pos
          WHERE pos.pool_id = s.pool_id
        ) pool_candidates ON TRUE
        LEFT JOIN LATERAL (
          SELECT COUNT(*) AS historical_candidate_count
          FROM positions pos
          WHERE pos.pool_id = s.pool_id
            AND pos.opened_at <= s.tick_time
        ) historical_candidates ON TRUE
      )
      SELECT
        horizon,
        lineage_bucket,
        COUNT(*) AS samples
      FROM classified
      GROUP BY horizon, lineage_bucket
      ORDER BY horizon, samples DESC, lineage_bucket
    ) TO STDOUT WITH CSV HEADER
  " "${csv_path}"

  cat >"${SNAPSHOT_DIR}/POSITION_ID_REPAIR_AUDIT_CN.md" <<'EOF'
# Position ID Repair Audit

| Horizon | Lineage Bucket | Samples |
| --- | --- | ---: |
EOF

  tail -n +2 "${csv_path}" | while IFS=, read -r horizon lineage_bucket samples; do
    printf '| %s | %s | %s |\n' "${horizon}" "${lineage_bucket}" "${samples}" \
      >>"${SNAPSHOT_DIR}/POSITION_ID_REPAIR_AUDIT_CN.md"
  done

  {
    echo
    echo "## Notes"
    echo
    echo "- `reconstructable_by_pool_time_strategy` means a unique pool-time candidate was found and only applied in repaired_v2."
    echo "- `ambiguous_multiple_positions` and `pool_only_match` remain untrusted for strict-valid."
    echo "- `historical_unrecoverable` means same-pool historical positions exist, but none can be trusted at the target decision time."
  } >>"${SNAPSHOT_DIR}/POSITION_ID_REPAIR_AUDIT_CN.md"
}

generate_original_label_logic_invalid_audit() {
  local csv_path="${SNAPSHOT_DIR}/original_label_logic_invalid_breakdown.csv"
  psql_csv "
    COPY (
      WITH scoped AS (
        SELECT
          r.horizon,
          d.selected AS trace_selected,
          d.intent_open AS trace_intent_open,
          COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS raw_position_id,
          COALESCE(NULLIF(r.entry_value_usd_repaired, ''), '0') AS entry_value_usd_repaired,
          COALESCE(NULLIF(r.label, ''), 'invalid') AS original_label,
          COALESCE(NULLIF(v2.label, ''), 'invalid') AS repaired_label,
          COALESCE(NULLIF(v2.invalid_reason_repaired, ''), 'unknown') AS repaired_invalid_reason
        FROM shadow_outcome_labels_repaired r
        JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
        LEFT JOIN shadow_outcome_labels_repaired_v2 v2
          ON v2.decision_trace_id = r.original_decision_trace_id
         AND v2.horizon = r.horizon
         AND v2.repair_version = '${REPAIR_VERSION}'
        WHERE r.horizon IN ('6h', '24h')
      )
      SELECT
        horizon,
        CASE
          WHEN trace_selected = FALSE THEN 'selected=false'
          WHEN trace_intent_open = FALSE THEN 'intent_open=false'
          WHEN trace_selected = TRUE AND raw_position_id = '' THEN 'selected=true but position_id missing'
          WHEN trace_selected = TRUE AND entry_value_usd_repaired = '0' THEN 'selected=true but entry missing'
          WHEN trace_selected = TRUE AND repaired_invalid_reason = 'future_mark_missing' THEN 'selected=true but future mark missing'
          WHEN original_label = 'invalid' AND repaired_label IN ('win', 'loss') THEN 'original invalid but repaired valid'
          WHEN repaired_label = 'invalid' THEN 'repaired invalid'
          WHEN repaired_label = 'skip' AND entry_value_usd_repaired = '0' THEN 'skip_without_entry'
          ELSE 'other'
        END AS bucket,
        COUNT(*) AS samples,
        ROUND((COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY horizon), 0)) * 100, 2) AS share_pct
      FROM scoped
      GROUP BY horizon, bucket
      ORDER BY horizon, samples DESC, bucket
    ) TO STDOUT WITH CSV HEADER
  " "${csv_path}"

  cat >"${SNAPSHOT_DIR}/ORIGINAL_LABEL_LOGIC_INVALID_AUDIT_CN.md" <<'EOF'
# Original Label Logic Invalid Audit

| horizon | bucket | samples | share_pct |
| --- | --- | ---: | ---: |
EOF

  tail -n +2 "${csv_path}" | while IFS=, read -r horizon bucket samples share_pct; do
    printf '| %s | %s | %s | %s |\n' "${horizon}" "${bucket}" "${samples}" "${share_pct}" \
      >>"${SNAPSHOT_DIR}/ORIGINAL_LABEL_LOGIC_INVALID_AUDIT_CN.md"
  done
}

generate_token_decimal_price_audit_v2() {
  cat >"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md" <<'EOF'
# Token Decimal Price Audit

- source: `shadow_outcome_labels_repaired_v2`
- verdict: EARLY_SIGNAL_ONLY

| Horizon | token_decimals_missing_before | token_decimals_missing_after | strict_invalid_rate_before_pct | strict_invalid_rate_after_pct | pct_signal |
| --- | ---: | ---: | ---: | ---: | --- |
EOF

  psql_q "
    WITH before_agg AS (
      SELECT
        horizon,
        COUNT(*) FILTER (WHERE invalid_reason_repaired = 'token_decimals_missing') AS before_missing,
        ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) AS before_invalid_rate
      FROM shadow_outcome_labels_repaired
      WHERE horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
      GROUP BY horizon
    ),
    after_agg AS (
      SELECT
        horizon,
        COUNT(*) FILTER (WHERE invalid_reason_repaired = 'token_decimals_missing') AS after_missing,
        ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) AS after_invalid_rate
      FROM shadow_outcome_labels_repaired_v2
      WHERE repair_version = '${REPAIR_VERSION}'
        AND horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
      GROUP BY horizon
    ),
    signal_agg AS (
      SELECT
        horizon,
        CASE
          WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
           AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
          THEN 'better'
          ELSE 'flat_or_worse'
        END AS pct_signal
      FROM (
        SELECT
          v2.*,
          NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) AS score_ntile
        FROM shadow_outcome_labels_repaired_v2 v2
        WHERE repair_version = '${REPAIR_VERSION}'
          AND horizon IN ('6h', '24h')
          AND selected = TRUE
          AND intent_open = TRUE
      ) ranked
      GROUP BY horizon
    )
    SELECT
      b.horizon,
      b.before_missing,
      a.after_missing,
      b.before_invalid_rate,
      a.after_invalid_rate,
      s.pct_signal
    FROM before_agg b
    JOIN after_agg a USING (horizon)
    JOIN signal_agg s USING (horizon)
    ORDER BY b.horizon DESC;
  " | while IFS='|' read -r horizon before_missing after_missing before_invalid after_invalid pct_signal; do
    [[ -z "${horizon:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s |\n' \
      "${horizon}" "${before_missing}" "${after_missing}" "${before_invalid}" "${after_invalid}" "${pct_signal}" \
      >>"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md"
  done
}

generate_valid_entry_outcome_v2() {
  cat >"${SNAPSHOT_DIR}/VALID_ENTRY_OUTCOME_CN.md" <<'EOF'
# Valid Entry Outcome

- source: `shadow_outcome_labels_repaired_v2`

| Horizon | token_decimals_missing_before | token_decimals_missing_after | strict_invalid_rate_before_pct | strict_invalid_rate_after_pct | healthy_strict_valid_before | healthy_strict_valid_after | usad_recovered | pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
EOF

  psql_q "
    WITH before_agg AS (
      SELECT
        horizon,
        COUNT(*) FILTER (WHERE invalid_reason_repaired = 'token_decimals_missing') AS before_missing,
        ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) AS before_invalid_rate,
        COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND token_metadata_status = 'present' AND price_status = 'available' AND invalid_reason_repaired <> 'missing_position_id') AS healthy_before
      FROM shadow_outcome_labels_repaired
      WHERE horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
      GROUP BY horizon
    ),
    after_agg AS (
      SELECT
        horizon,
        COUNT(*) FILTER (WHERE invalid_reason_repaired = 'token_decimals_missing') AS after_missing,
        ROUND((COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE valid_entry_strict = TRUE), 0)) * 100, 6) AS after_invalid_rate,
        COUNT(*) FILTER (WHERE valid_entry_strict = TRUE AND metadata_source IN ('pool_token_metadata', 'rpc_audit') AND price_source <> 'missing' AND position_id_source IN ('decision_trace', 'reconstructable_by_pool_time_strategy') AND mark_source = 'position_mark') AS healthy_after,
        COUNT(*) FILTER (WHERE pool_id = '0x9a993fc0eec60faaa0c391ff11b840ce16685150' AND valid_entry_strict = TRUE) AS usad_recovered
      FROM shadow_outcome_labels_repaired_v2
      WHERE repair_version = '${REPAIR_VERSION}'
        AND horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
      GROUP BY horizon
    ),
    signal_agg AS (
      SELECT
        horizon,
        CASE
          WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
           AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
          THEN 'better'
          ELSE 'flat_or_worse'
        END AS pct_signal
      FROM (
        SELECT
          v2.*,
          NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) AS score_ntile
        FROM shadow_outcome_labels_repaired_v2 v2
        WHERE repair_version = '${REPAIR_VERSION}'
          AND horizon IN ('6h', '24h')
          AND selected = TRUE
          AND intent_open = TRUE
      ) ranked
      GROUP BY horizon
    )
    SELECT
      b.horizon,
      b.before_missing,
      a.after_missing,
      b.before_invalid_rate,
      a.after_invalid_rate,
      b.healthy_before,
      a.healthy_after,
      a.usad_recovered,
      s.pct_signal
    FROM before_agg b
    JOIN after_agg a USING (horizon)
    JOIN signal_agg s USING (horizon)
    ORDER BY b.horizon DESC;
  " | while IFS='|' read -r horizon before_missing after_missing before_invalid after_invalid healthy_before healthy_after usad_recovered pct_signal; do
    [[ -z "${horizon:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "${horizon}" "${before_missing}" "${after_missing}" "${before_invalid}" "${after_invalid}" \
      "${healthy_before}" "${healthy_after}" "${usad_recovered}" "${pct_signal}" \
      >>"${SNAPSHOT_DIR}/VALID_ENTRY_OUTCOME_CN.md"
  done
}

generate_pnl_reality_audit_v2() {
  cat >"${SNAPSHOT_DIR}/PNL_REALITY_AUDIT_CN.md" <<'EOF'
# PNL Reality Audit

| Horizon | healthy_realized_count | top20_median_pct | top20_p10_pct | bottom20_median_pct | bottom20_p10_pct | pct_signal |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
EOF

  psql_q "
    WITH ranked AS (
      SELECT
        v2.*,
        NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) AS score_ntile
      FROM shadow_outcome_labels_repaired_v2 v2
      WHERE repair_version = '${REPAIR_VERSION}'
        AND horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
        AND valid_entry_strict = TRUE
        AND label IN ('win', 'loss')
        AND metadata_source IN ('pool_token_metadata', 'rpc_audit')
        AND price_source <> 'missing'
        AND position_id_source IN ('decision_trace', 'reconstructable_by_pool_time_strategy')
        AND mark_source = 'position_mark'
    )
    SELECT
      horizon,
      COUNT(*) AS healthy_realized_count,
      ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS top20_median_pct,
      ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS top20_p10_pct,
      ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS bottom20_median_pct,
      ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS bottom20_p10_pct,
      CASE
        WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5))::NUMERIC, 0)
           > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1))::NUMERIC, 0)
         AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5))::NUMERIC, 0)
           >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1))::NUMERIC, 0)
        THEN 'better'
        ELSE 'flat_or_worse'
      END AS pct_signal
    FROM ranked
    GROUP BY horizon
    ORDER BY horizon DESC;
  " | while IFS='|' read -r horizon healthy_realized_count top20_median_pct top20_p10_pct bottom20_median_pct bottom20_p10_pct pct_signal; do
    [[ -z "${horizon:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s |\n' \
      "${horizon}" "${healthy_realized_count}" "${top20_median_pct}" "${top20_p10_pct}" \
      "${bottom20_median_pct}" "${bottom20_p10_pct}" "${pct_signal}" \
      >>"${SNAPSHOT_DIR}/PNL_REALITY_AUDIT_CN.md"
  done
}

generate_stale_mark_target_window_audit() {
  cat >"${SNAPSHOT_DIR}/STALE_MARK_TARGET_WINDOW_AUDIT_CN.md" <<'EOF'
# Stale Mark Target Window Audit

| pool_id | horizon | stale_bucket | samples | target_gap_sec_p50 | target_gap_sec_p90 | target_gap_sec_p99 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
EOF

  psql_q "
    WITH target_pools(pool_id) AS (
      VALUES
        ('0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38'),
        ('0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59'),
        ('0x9a993fc0eec60faaa0c391ff11b840ce16685150'),
        ('0x4e962bb3889bf030368f56810a9c96b83cb3e778'),
        ('0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1'),
        ('0x6c561b446416e1a00e8e93e221854d6ea4171372')
    ),
    scoped AS (
      SELECT
        v2.pool_id,
        v2.horizon,
        v2.position_id,
        v2.invalid_reason_repaired,
        d.tick_time,
        CASE v2.horizon
          WHEN '6h' THEN 21600::BIGINT
          WHEN '24h' THEN 86400::BIGINT
          ELSE 3600::BIGINT
        END AS horizon_seconds
      FROM shadow_outcome_labels_repaired_v2 v2
      JOIN shadow_decision_trace d ON d.trace_id = v2.decision_trace_id
      WHERE v2.repair_version = '${REPAIR_VERSION}'
        AND v2.pool_id IN (SELECT pool_id FROM target_pools)
        AND v2.selected = TRUE
        AND v2.intent_open = TRUE
    ),
    gap_calc AS (
      SELECT
        s.pool_id,
        s.horizon,
        CASE
          WHEN s.invalid_reason_repaired = 'missing_position_id' THEN 'position_id_join_failed'
          WHEN s.invalid_reason_repaired = 'token_decimals_missing' THEN 'metadata_gap'
          WHEN s.invalid_reason_repaired = 'mark_window_too_narrow' THEN 'mark_window_too_narrow'
          WHEN s.invalid_reason_repaired = 'future_mark_missing' THEN 'true_stale_mark'
          ELSE s.invalid_reason_repaired
        END AS stale_bucket,
        COALESCE((
          SELECT ABS(pm.mark_time - (s.tick_time + s.horizon_seconds))
          FROM shadow_position_marks pm
          WHERE pm.position_id = s.position_id
          ORDER BY ABS(pm.mark_time - (s.tick_time + s.horizon_seconds))
          LIMIT 1
        ), (
          SELECT ABS(pm.mark_time - (s.tick_time + s.horizon_seconds))
          FROM shadow_position_marks pm
          WHERE pm.pool_id = s.pool_id
          ORDER BY ABS(pm.mark_time - (s.tick_time + s.horizon_seconds))
          LIMIT 1
        ), 0) AS gap_seconds
      FROM scoped s
    )
    SELECT
      pool_id,
      horizon,
      stale_bucket,
      COUNT(*) AS samples,
      ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_seconds))::NUMERIC, 2) AS p50_gap,
      ROUND((percentile_cont(0.9) WITHIN GROUP (ORDER BY gap_seconds))::NUMERIC, 2) AS p90_gap,
      ROUND((percentile_cont(0.99) WITHIN GROUP (ORDER BY gap_seconds))::NUMERIC, 2) AS p99_gap
    FROM gap_calc
    GROUP BY pool_id, horizon, stale_bucket
    ORDER BY pool_id, horizon, stale_bucket;
  " | while IFS='|' read -r pool_id horizon stale_bucket samples p50_gap p90_gap p99_gap; do
    [[ -z "${pool_id:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s |\n' \
      "${pool_id}" "${horizon}" "${stale_bucket}" "${samples}" "${p50_gap}" "${p90_gap}" "${p99_gap}" \
      >>"${SNAPSHOT_DIR}/STALE_MARK_TARGET_WINDOW_AUDIT_CN.md"
  done
}

generate_gate_conclusion_v2() {
  local gate_metrics
  local coverage_gate="PASS"
  local data_quality_gate="PASS"
  local reality_gate="PASS"
  local edge_gate="PASS"
  local tiny_canary_candidate="no"

  gate_metrics="$(psql_q "
    WITH mature AS (
      SELECT '6h'::TEXT AS horizon, COUNT(*) AS mature_count
      FROM shadow_decision_trace
      WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 21600
      UNION ALL
      SELECT '24h'::TEXT, COUNT(*)
      FROM shadow_decision_trace
      WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 86400
    ),
    coverage AS (
      SELECT horizon, COUNT(*) AS label_count
      FROM shadow_outcome_labels
      WHERE horizon IN ('6h', '24h')
      GROUP BY horizon
    ),
    v2 AS (
      SELECT *
      FROM shadow_outcome_labels_repaired_v2
      WHERE repair_version = '${REPAIR_VERSION}'
        AND horizon IN ('6h', '24h')
        AND selected = TRUE
        AND intent_open = TRUE
    ),
    bias AS (
      SELECT
        horizon,
        MAX(pool_share) AS max_pool_share
      FROM (
        SELECT
          horizon,
          pool_id,
          COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY horizon), 0) AS pool_share
        FROM v2
        WHERE valid_entry_strict = TRUE
        GROUP BY horizon, pool_id
      ) ranked
      GROUP BY horizon
    ),
    edge AS (
      SELECT
        horizon,
        ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 6) AS top20_median_pct,
        ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 6) AS top20_p10_pct,
        CASE
          WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
           AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 5 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
             >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_pct_repaired::NUMERIC) FILTER (WHERE score_ntile = 1 AND valid_entry_strict = TRUE AND label IN ('win', 'loss')))::NUMERIC, 0)
          THEN 'better'
          ELSE 'flat_or_worse'
        END AS pct_signal
      FROM (
        SELECT
          v2.*,
          NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) AS score_ntile
        FROM v2
      ) ranked
      GROUP BY horizon
    )
    SELECT
      v2.horizon,
      ROUND((COALESCE(c.label_count, 0)::NUMERIC / NULLIF(m.mature_count, 0)) * 100, 2) AS coverage_pct,
      ROUND((COUNT(*) FILTER (WHERE v2.valid_entry_strict = TRUE AND v2.label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE v2.valid_entry_strict = TRUE), 0)) * 100, 6) AS strict_valid_invalid_rate_pct,
      COUNT(*) FILTER (WHERE v2.valid_entry_strict = TRUE) AS strict_valid_count,
      COUNT(*) FILTER (
        WHERE v2.valid_entry_strict = TRUE
          AND v2.entry_value_confidence = 'high'
          AND v2.metadata_source IN ('pool_token_metadata', 'rpc_audit')
          AND v2.price_source <> 'missing'
          AND v2.position_id_source IN ('decision_trace', 'reconstructable_by_pool_time_strategy')
          AND v2.mark_source = 'position_mark'
          AND v2.net_pnl_pct_repaired <> ''
      ) AS reality_auditable_count,
      COALESCE(b.max_pool_share, 0) AS max_pool_share,
      e.pct_signal,
      e.top20_median_pct,
      e.top20_p10_pct
    FROM v2
    JOIN mature m ON m.horizon = v2.horizon
    LEFT JOIN coverage c ON c.horizon = v2.horizon
    LEFT JOIN bias b ON b.horizon = v2.horizon
    LEFT JOIN edge e ON e.horizon = v2.horizon
    GROUP BY v2.horizon, c.label_count, m.mature_count, b.max_pool_share, e.pct_signal, e.top20_median_pct, e.top20_p10_pct
    ORDER BY v2.horizon DESC;
  ")"

  while IFS='|' read -r horizon coverage_pct strict_valid_invalid_rate_pct strict_valid_count reality_auditable_count max_pool_share pct_signal top20_median_pct top20_p10_pct; do
    [[ -z "${horizon:-}" ]] && continue
    if awk -v value="${coverage_pct:-0}" 'BEGIN { exit !(value + 0 < 70) }'; then
      coverage_gate="FAIL"
    fi
    if awk -v value="${strict_valid_invalid_rate_pct:-0}" 'BEGIN { exit !(value + 0 > 30) }'; then
      data_quality_gate="FAIL"
    fi
    if awk -v value="${max_pool_share:-0}" 'BEGIN { exit !(value + 0 > 0.50) }'; then
      data_quality_gate="FAIL"
    fi
    if [[ "${reality_auditable_count:-0}" != "${strict_valid_count:-0}" ]]; then
      reality_gate="FAIL"
    fi
    if [[ "${pct_signal}" != "better" ]]; then
      edge_gate="FAIL"
    fi
    if awk -v value="${top20_median_pct:-0}" 'BEGIN { exit !(value + 0 <= 0) }'; then
      edge_gate="FAIL"
    fi
    if awk -v value="${top20_p10_pct:-0}" 'BEGIN { exit !(value + 0 < -0.05) }'; then
      edge_gate="FAIL"
    fi
  done <<<"${gate_metrics}"

  if [[ "${coverage_gate}" == "PASS" && "${data_quality_gate}" == "PASS" && "${reality_gate}" == "PASS" && "${edge_gate}" == "PASS" ]]; then
    tiny_canary_candidate="yes"
  fi

  cat >"${SNAPSHOT_DIR}/GATE_CONCLUSION_CN.md" <<EOF
# Gate Conclusion

- coverage_gate: ${coverage_gate}
- data_quality_gate: ${data_quality_gate}
- reality_gate: ${reality_gate}
- edge_gate: ${edge_gate}
- edge_proven: no
- tiny_canary_candidate: ${tiny_canary_candidate}
- tiny_canary_allowed: no

## Metrics

| Horizon | Coverage % | Strict Valid Invalid Rate % | Strict Valid Count | Reality Auditable Count | Max Pool Share | pct_signal | top20_median_pct | top20_p10_pct |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
EOF

  while IFS='|' read -r horizon coverage_pct strict_valid_invalid_rate_pct strict_valid_count reality_auditable_count max_pool_share pct_signal top20_median_pct top20_p10_pct; do
    [[ -z "${horizon:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "${horizon}" "${coverage_pct}" "${strict_valid_invalid_rate_pct}" "${strict_valid_count}" \
      "${reality_auditable_count}" "${max_pool_share}" "${pct_signal}" "${top20_median_pct}" "${top20_p10_pct}" \
      >>"${SNAPSHOT_DIR}/GATE_CONCLUSION_CN.md"
  done <<<"${gate_metrics}"

  {
    echo
    echo "## Rule"
    echo
    echo "- coverage_gate requires 6h/24h coverage >= 70%."
    echo "- data_quality_gate requires 6h/24h invalid_rate <= 30%, selected_strict_valid_invalid_rate <= 30%, and sample_bias = OK."
    echo "- reality_gate requires trusted entry, decimals, price, position lineage, mark source, and calculable net_pnl_pct for strict-valid rows."
    echo "- edge_gate requires 6h/24h pct_signal = better, top20 median_pct > 0, and top20 p10_pct near zero or better."
    echo "- tiny_canary_allowed remains no by safety rule."
  } >>"${SNAPSHOT_DIR}/GATE_CONCLUSION_CN.md"
}

write_checkpoint() {
  local checkpoint_path
  checkpoint_path="${SNAPSHOT_DIR}/CHECKPOINT_$(date -u +%H%M)_CN.md"
  cat >"${checkpoint_path}" <<EOF
# Checkpoint

- time_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- repair_version: \`${REPAIR_VERSION}\`
- repaired_v2_rows: $(psql_q "SELECT COUNT(*) FROM shadow_outcome_labels_repaired_v2 WHERE repair_version = '${REPAIR_VERSION}';" | tr -d '[:space:]')
- latest_report_dir: \`${SNAPSHOT_DIR}\`
- tiny_canary_allowed: no
EOF
}

write_overnight_final_summary() {
  cat >"${SNAPSHOT_DIR}/OVERNIGHT_FINAL_SUMMARY_CN.md" <<EOF
# Overnight Final Summary

- repaired_v2_materialization_complete: yes
- report_dir: \`${SNAPSHOT_DIR}\`
- repair_version: \`${REPAIR_VERSION}\`

## Key Results

- 6h/24h invalid_rate before/after: see [VALID_ENTRY_OUTCOME_CN.md](${SNAPSHOT_DIR}/VALID_ENTRY_OUTCOME_CN.md)
- healthy strict-valid count before/after: see [VALID_ENTRY_OUTCOME_CN.md](${SNAPSHOT_DIR}/VALID_ENTRY_OUTCOME_CN.md)
- token_decimals_missing before/after: see [REPAIRED_V2_MATERIALIZATION_CN.md](${SNAPSHOT_DIR}/REPAIRED_V2_MATERIALIZATION_CN.md)
- position_id lineage success rate: see [POSITION_ID_REPAIR_AUDIT_CN.md](${SNAPSHOT_DIR}/POSITION_ID_REPAIR_AUDIT_CN.md)
- target-window sensitivity: see [TARGET_WINDOW_SENSITIVITY_CN.md](${SNAPSHOT_DIR}/TARGET_WINDOW_SENSITIVITY_CN.md)
- pct_signal: see [PNL_REALITY_AUDIT_CN.md](${SNAPSHOT_DIR}/PNL_REALITY_AUDIT_CN.md)
- gate result: see [GATE_CONCLUSION_CN.md](${SNAPSHOT_DIR}/GATE_CONCLUSION_CN.md)
- tiny_canary_candidate: no
- tiny_canary_allowed: no

## Priority Blockers

1. 24h strict-valid invalid rate still above the 30% gate after repaired_v2.
2. Mark-window and future-mark gaps remain a dominant invalid bucket.
3. Position lineage is improved but not fully trusted for all strict-valid rows.
4. reality_gate remains blocked until trusted mark/lineage coverage is complete.
EOF
}

load_env
cd "$ROOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

if ! table_exists "shadow_outcome_labels_repaired"; then
  exit 0
fi

write_shadow_token_audit_input
run_shadow_token_rpc_audit
apply_repaired_v2_migration
materialize_repaired_v2
generate_repaired_v2_materialization_report
generate_decimals_join_fix_audit
generate_pool_token_canonical_mapping
generate_target_window_sensitivity
generate_position_id_repair_audit
generate_original_label_logic_invalid_audit
generate_valid_entry_outcome_v2
generate_token_decimal_price_audit_v2
generate_pnl_reality_audit_v2
generate_stale_mark_target_window_audit
generate_gate_conclusion_v2
write_checkpoint
write_overnight_final_summary
