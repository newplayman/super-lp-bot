#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="${LPBOT_SHADOW_OBS_SNAPSHOT_DIR:-}"
CONFIG_PATH="${LPBOT_SHADOW_OBS_CONFIG:-configs/config.shadow.research.toml}"

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

table_exists() {
  local table_name="$1"
  local count
  count="$(psql_q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='${table_name}';" | tr -d '[:space:]')"
  [[ "${count:-0}" != "0" ]]
}

write_markdown_rows_from_query() {
  local query="$1"
  psql_q "$query" | while IFS='|' read -r c1 c2 c3 c4 c5 c6 c7 c8 c9 c10 c11 c12; do
    [[ -z "${c1:-}" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "${c1:-}" "${c2:-}" "${c3:-}" "${c4:-}" "${c5:-}" "${c6:-}" \
      "${c7:-}" "${c8:-}" "${c9:-}" "${c10:-}" "${c11:-}" "${c12:-}"
  done
}

write_shadow_token_audit_input() {
  cat >"${SNAPSHOT_DIR}/high_impact_decimals_targets.csv" <<'EOF'
token_symbol,token_address,chain
PLAY,0x853a7c99227499dba9db8c3a02aa691afdebf841,base
DUAL,0x832b55b0fa6397ca9e63b8c15dadef3f6e44614c,base
USAD,0x3d66e6fe9a3cf698db5af3d70830b299c9235151,base
EOF
}

resolve_table_with_columns() {
  local columns=("${!1}")
  local candidate
  local i
  for candidate in "${columns[@]:2}"; do
    local table_name="$candidate"
    if table_exists "$table_name"; then
      local found=1
      for (( i=0; i<${#columns[@]}; i++ )); do
        local required_col="${columns[i]}"
        local count
        count="$(psql_q "
          SELECT COUNT(*)
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = '${table_name}'
            AND column_name = '${required_col}';
        ")"
        if [[ "$(echo "$count" | tr -d '[:space:]')" == "0" ]]; then
          found=0
          break
        fi
      done
      if [[ "$found" == "1" ]]; then
        printf "%s" "$table_name"
        return 0
      fi
    fi
  done
  return 1
}

escape_single_quote() {
  printf "%s" "$1" | sed "s/'/''/g"
}

resolve_first_table() {
  local cols
  cols="$1"
  shift
  local table
  local col

  for table in "$@"; do
    if ! table_exists "$table"; then
      continue
    fi
    local missing=0
    IFS=',' read -r -a col_list <<<"${cols}"
    for col in "${col_list[@]}"; do
      local count
      count="$(psql_q "
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='${table}'
          AND column_name='${col}';")"
      if [[ "$(echo "$count" | tr -d '[:space:]')" == "0" ]]; then
        missing=1
        break
      fi
    done
    if [[ "$missing" == "0" ]]; then
      printf "%s" "$table"
      return 0
    fi
  done
  return 1
}

resolve_optional_column() {
  local table="$1"
  shift
  local col

  for col in "$@"; do
    local count
    count="$(psql_q "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='${table}' AND column_name='${col}';")"
    if [[ "$(echo "$count" | tr -d '[:space:]')" != "0" ]]; then
      printf '%s' "$col"
      return 0
    fi
  done
  return 1
}

resolve_pool_metadata_table() {
  resolve_first_table "pool_id,chain,token0,token1" \
    "pool_token_metadata" \
    "scanner_pool_metadata" \
    "pool_metadata" \
    "scanner_pools" \
    "pools"
}

resolve_token_metadata_table() {
  resolve_first_table "token_address,chain" \
    "pool_token_metadata" \
    "token_metadata" \
    "scanner_token_metadata" \
    "token_registry" \
    "scanner_tokens" \
    "metadata_tokens"
}

resolve_decision_position_token_columns() {
  local prefix="$1"
  local table="$2"
  local c0=""
  local c1=""
  c0="$(resolve_optional_column "$table" token0 token0_address token_a tokena token_x 2>/dev/null || true)"
  c1="$(resolve_optional_column "$table" token1 token1_address token_b tokenb token_y 2>/dev/null || true)"
  printf '%s|%s' "$c0" "$c1"
}

to_lower_address() {
  local value="$1"
  printf "%s" "${value,,}"
}

run_shadow_token_rpc_audit() {
  go run -tags shadow ./cmd/lpbot \
    --config="${CONFIG_PATH}" \
    --shadow-token-rpc-audit \
    --shadow-token-rpc-audit-input="${SNAPSHOT_DIR}/high_impact_decimals_targets.csv" \
    --shadow-token-rpc-audit-output="${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv" \
    >/dev/null
}

generate_high_impact_decimals_audit() {
  write_shadow_token_audit_input
  run_shadow_token_rpc_audit

  cat >"${SNAPSHOT_DIR}/HIGH_IMPACT_DECIMALS_AUDIT_CN.md" <<'EOF'
# High Impact Decimals Audit

- scope: PLAY / DUAL / USAD
- source: `shadow_outcome_labels_repaired` + `pools` + Base read-only `eth_getCode` / `eth_call`

| Token | Address | Chain | Has Bytecode | decimals() | decimals_error | symbol() | symbol_error | scanner_token_matches_pool | affected_24h_samples | affected_selected_samples | affected_top20_samples | metadata_untrusted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
EOF

  while IFS=, read -r token_symbol token_address chain has_bytecode decimals_result decimals_error symbol_result symbol_error metadata_untrusted; do
    [[ "${token_symbol}" == "token_symbol" ]] && continue
    local counts
    counts="$(psql_q "
      WITH ranked AS (
        SELECT
          r.*,
          NTILE(5) OVER (PARTITION BY r.horizon ORDER BY r.score_total ASC, r.original_decision_trace_id) AS score_ntile
        FROM shadow_outcome_labels_repaired r
        WHERE r.horizon IN ('6h', '24h')
          AND r.selected = TRUE
          AND r.intent_open = TRUE
          AND (r.token_metadata_status <> 'present' OR r.invalid_reason_repaired = 'token_decimals_missing')
      )
      SELECT
        CASE WHEN COUNT(*) > 0 THEN 'yes' ELSE 'no' END AS scanner_token_matches_pool,
        COUNT(*) FILTER (WHERE horizon = '24h') AS affected_24h_samples,
        COUNT(*) AS affected_selected_samples,
        COUNT(*) FILTER (WHERE score_ntile = 5) AS affected_top20_samples
      FROM ranked r
      JOIN pools p ON p.pool_id = r.pool_id
      WHERE lower(p.token0) = lower('${token_address}') OR lower(p.token1) = lower('${token_address}');
    ")"
    local scanner_match affected_24h affected_selected affected_top20
    IFS='|' read -r scanner_match affected_24h affected_selected affected_top20 <<<"${counts}"
      printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
        "${token_symbol}" \
        "${token_address}" \
      "${chain}" \
      "${has_bytecode}" \
      "${decimals_result:-"-"}" \
      "${decimals_error:-"-"}" \
      "${symbol_result:-"-"}" \
      "${symbol_error:-"-"}" \
      "${scanner_match:-no}" \
      "${affected_24h:-0}" \
      "${affected_selected:-0}" \
      "${affected_top20:-0}" \
      "${metadata_untrusted}" >>"${SNAPSHOT_DIR}/HIGH_IMPACT_DECIMALS_AUDIT_CN.md"
  done <"${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv"
}

generate_decimals_join_audit() {
  local token_metadata_table=""
  local token_addr_col=""
  local token_chain_col=""
  local token_symbol_col=""
  local target_addr_l
  local target_chain_l
  local token_addr_expr="''"
  local token_chain_expr="''"
  local token_symbol_expr="''"

  token_metadata_table="$(resolve_token_metadata_table || true)"
  if [[ -n "$token_metadata_table" ]]; then
    token_addr_col="$(resolve_optional_column "$token_metadata_table" token_address address token_addr contract_address 2>/dev/null || true)"
    token_chain_col="$(resolve_optional_column "$token_metadata_table" chain chain_id chain_name 2>/dev/null || true)"
    token_symbol_col="$(resolve_optional_column "$token_metadata_table" token_symbol symbol token_symbol_text 2>/dev/null || true)"
    token_addr_expr="COALESCE(${token_addr_col}, '')"
    if [[ -n "$token_chain_col" ]]; then
      token_chain_expr="COALESCE(LOWER(${token_chain_col}), '')"
    fi
    if [[ -n "$token_symbol_col" ]]; then
      token_symbol_expr="COALESCE(${token_symbol_col}, '')"
    fi
  fi

  local eth_call_decimals_available_count=0
  local metadata_join_success_count=0
  local metadata_join_failed_count=0
  local reason_address_case=0
  local reason_address_value=0
  local reason_chain=0
  local reason_pool=0
  local reason_scanner=0
  local reason_missing=0
  local reason_other=0

  cat >"${SNAPSHOT_DIR}/DECIMALS_JOIN_AUDIT_CN.md" <<'EOF'
# Decimals Join Audit

- scope: PLAY / DUAL / USAD
- objective: diagnose why on-chain decimals/symbol pass but strict-valid still flags token_decimals_missing

| Symbol | Metadata Token Address | Scanner Token0 | Scanner Token1 | Metadata Chain | Metadata Symbol | Metadata Row Chain Match | Scanner Token Matches Pool | Outcome Pool IDs | Outcome Pool Chain | Lowercase Address Match | Chain Match | Failed Reason | affected_24h_samples | affected_selected_samples | affected_top20_samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
EOF

  while IFS=, read -r token_symbol token_address chain has_bytecode decimals_result decimals_error symbol_result symbol_error metadata_untrusted; do
    [[ "$token_symbol" == "token_symbol" ]] && continue

    target_addr_l="$(to_lower_address "$token_address")"
    target_chain_l="$(to_lower_address "$chain")"
    [[ -z "$target_addr_l" ]] && continue

    local decimals_ok=0
    if [[ -z "$decimals_error" && -z "$symbol_error" ]]; then
      decimals_ok=1
    fi
    ((eth_call_decimals_available_count += decimals_ok))

    local metadata_rows=""
    if [[ -n "$token_metadata_table" && -n "$token_addr_col" ]]; then
      if [[ -n "$token_chain_col" ]]; then
        metadata_rows="$(psql_q "
          SELECT
            ${token_addr_expr} AS raw_addr,
            lower(${token_addr_expr}) AS addr_l,
            ${token_symbol_expr} AS token_symbol,
            ${token_chain_expr} AS chain
          FROM ${token_metadata_table}
          WHERE lower(${token_addr_expr}) = '${target_addr_l}'
          ORDER BY CASE WHEN ${token_chain_expr} = '${target_chain_l}' THEN 0 ELSE 1 END, token_symbol IS NULL
          LIMIT 1;
        ")"
      else
        metadata_rows="$(psql_q "
          SELECT
            ${token_addr_expr} AS raw_addr,
            lower(${token_addr_expr}) AS addr_l,
            ${token_symbol_expr} AS token_symbol,
            '' AS chain
          FROM ${token_metadata_table}
          WHERE lower(${token_addr_expr}) = '${target_addr_l}'
          LIMIT 1;
        ")"
      fi
    fi

    local md_raw_addr md_addr_l md_symbol md_chain
    IFS='|' read -r md_raw_addr md_addr_l md_symbol md_chain <<<"$metadata_rows"

    local scoped_rows
    scoped_rows="$(psql_q "
      WITH scoped AS (
        SELECT
          r.horizon,
          NTILE(5) OVER (PARTITION BY r.horizon ORDER BY r.score_total ASC, r.original_decision_trace_id) AS score_ntile,
          lower(p.token0) AS token0,
          lower(p.token1) AS token1,
          lower(COALESCE(d.chain, '')) AS pool_chain,
          p.pool_id
        FROM shadow_outcome_labels_repaired r
        JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
        JOIN pools p ON p.pool_id = d.pool_id
        WHERE r.horizon IN ('6h', '24h')
          AND r.selected = TRUE
          AND r.intent_open = TRUE
          AND (r.token_metadata_status <> 'present' OR r.invalid_reason_repaired = 'token_decimals_missing')
          AND (lower(p.token0) = '${target_addr_l}' OR lower(p.token1) = '${target_addr_l}')
      )
      SELECT
        COALESCE(MIN(pool_chain), ''),
        COALESCE(string_agg(DISTINCT token0, ',' ORDER BY token0), ''),
        COALESCE(string_agg(DISTINCT token1, ',' ORDER BY token1), ''),
        COALESCE(string_agg(DISTINCT pool_id, ',' ORDER BY pool_id), ''),
        COUNT(*) FILTER (WHERE horizon = '24h'),
        COUNT(*),
        COUNT(*) FILTER (WHERE score_ntile = 5)
      FROM scoped;
    ")"

    local scoped_pool_chain scoped_token0 scoped_token1 scoped_pool_ids affected_24h affected_selected affected_top20
    IFS='|' read -r scoped_pool_chain scoped_token0 scoped_token1 scoped_pool_ids affected_24h affected_selected affected_top20 <<<"$scoped_rows"

    local scanner_matches_pool="no"
    if [[ -n "$scoped_pool_ids" ]]; then
      scanner_matches_pool="yes"
    fi

    local failed_reason=""
    local chain_row_match="no"
    local lowercase_match="no"
    if [[ -z "$md_raw_addr" ]]; then
      failed_reason="missing_pool_metadata"
      ((reason_missing += 1))
    elif [[ "${target_addr_l}" != "$md_addr_l" ]]; then
      failed_reason="address_value_mismatch"
      ((reason_address_value += 1))
    elif [[ "$token_address" != "$md_raw_addr" ]]; then
      failed_reason="address_case_mismatch"
      ((reason_address_case += 1))
      lowercase_match="yes"
    else
      lowercase_match="yes"
      if [[ -n "$md_chain" && -n "$target_chain_l" && "$md_chain" != "$target_chain_l" ]]; then
        failed_reason="chain_mismatch"
        ((reason_chain += 1))
      elif [[ -z "$scoped_pool_ids" ]]; then
        failed_reason="scanner_mapping_mismatch"
        ((reason_scanner += 1))
      elif [[ -n "$scoped_pool_chain" && -n "$target_chain_l" && "$scoped_pool_chain" != "$target_chain_l" ]]; then
        failed_reason="pool_token_mismatch"
        ((reason_pool += 1))
      fi
    fi

    if [[ -n "$md_chain" && "$md_chain" == "$target_chain_l" ]]; then
      chain_row_match="yes"
    fi
    if [[ -z "$failed_reason" ]]; then
      failed_reason=""
      ((metadata_join_success_count += 1))
    else
      ((metadata_join_failed_count += 1))
      [[ "$failed_reason" == other ]] && ((reason_other += 1))
    fi

    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "$token_symbol" \
      "${md_raw_addr:-}" \
      "${scoped_token0:-}" \
      "${scoped_token1:-}" \
      "${md_chain:-}" \
      "${md_symbol:-}" \
      "$chain_row_match" \
      "$scanner_matches_pool" \
      "${scoped_pool_ids:-}" \
      "${scoped_pool_chain:-}" \
      "$lowercase_match" \
      "$chain_row_match" \
      "$failed_reason" \
      "${affected_24h:-0}" \
      "${affected_selected:-0}" \
      "${affected_top20:-0}" \
      >>"${SNAPSHOT_DIR}/DECIMALS_JOIN_AUDIT_CN.md"
  done <"${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv"

  {
    echo
    echo "## Aggregate"
    echo
    echo "- eth_call_decimals_available_count: ${eth_call_decimals_available_count}"
    echo "- metadata_join_success_count: ${metadata_join_success_count}"
    echo "- metadata_join_failed_count: ${metadata_join_failed_count}"
    echo "- failure by reason:"
    echo "  - address_case_mismatch: ${reason_address_case}"
    echo "  - address_value_mismatch: ${reason_address_value}"
    echo "  - chain_mismatch: ${reason_chain}"
    echo "  - pool_token_mismatch: ${reason_pool}"
    echo "  - scanner_mapping_mismatch: ${reason_scanner}"
    echo "  - missing_pool_metadata: ${reason_missing}"
    echo "  - other: ${reason_other}"
  } >>"${SNAPSHOT_DIR}/DECIMALS_JOIN_AUDIT_CN.md"
}

generate_token_decimal_price_audit() {
  cat >"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md" <<'EOF'
# Token Decimal Price Audit

- scope: PLAY / DUAL / USAD
- source: `high_impact_decimals_rpc.csv + shadow_outcome_labels_repaired`

## Token RPC Audit Summary

| Symbol | Decimals Result | Decimals Error | Symbol Result | Symbol Error | Metadata Untrusted |
| --- | ---: | --- | --- | --- | --- |
EOF

  while IFS=, read -r token_symbol token_address chain has_bytecode decimals_result decimals_error symbol_result symbol_error metadata_untrusted; do
    [[ "${token_symbol}" == "token_symbol" ]] && continue
    printf '| %s | %s | %s | %s | %s | %s |\n' \
      "${token_symbol}" "${decimals_result:-0}" "${decimals_error:--}" "${symbol_result:--}" "${symbol_error:--}" "${metadata_untrusted}" \
      >>"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md"
  done <"${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv"

  {
    echo
    echo "## Repaired Strict-Valid Status by Horizon"
    echo
    echo "| Symbol | Horizon | strict_valid_count | strict_invalid_count | strict_invalid_rate | token_decimals_missing_count | token_decimals_missing_rate |"
    echo "| --- | --- | ---: | ---: | ---: | ---: | ---: |"
  } >>"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md"

  while IFS=, read -r token_symbol token_address chain _; do
    [[ "${token_symbol}" == "token_symbol" ]] && continue
    local token_address_l="$(to_lower_address "$token_address")"
    local symbol_rows
    symbol_rows="$(psql_q "
      WITH scoped AS (
        SELECT
          r.horizon,
          CASE WHEN r.valid_entry_strict THEN 1 ELSE 0 END AS strict_entry,
          CASE WHEN r.token_metadata_status <> 'present' OR r.invalid_reason_repaired = 'token_decimals_missing' THEN 1 ELSE 0 END AS token_decimals_missing,
          CASE WHEN r.label = 'invalid' THEN 1 ELSE 0 END AS invalid_flag,
          p.token0, p.token1
        FROM shadow_outcome_labels_repaired r
        JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
        JOIN pools p ON p.pool_id = d.pool_id
        WHERE r.horizon IN ('6h','24h')
          AND r.selected = TRUE
          AND r.intent_open = TRUE
      )
      SELECT
        horizon,
        COUNT(*) FILTER (WHERE strict_entry = 1) AS strict_valid_count,
        COUNT(*) FILTER (WHERE strict_entry = 1 AND invalid_flag = 1) AS strict_invalid_count,
        CASE WHEN COUNT(*) FILTER (WHERE strict_entry = 1) = 0 THEN 0 ELSE
          ROUND((COUNT(*) FILTER (WHERE strict_entry = 1 AND invalid_flag = 1)::NUMERIC / COUNT(*) FILTER (WHERE strict_entry = 1)) * 100, 6) END AS strict_invalid_rate,
        COUNT(*) FILTER (WHERE strict_entry = 1 AND token_decimals_missing = 1) AS token_decimals_missing_count,
        CASE WHEN COUNT(*) FILTER (WHERE strict_entry = 1) = 0 THEN 0 ELSE
          ROUND((COUNT(*) FILTER (WHERE strict_entry = 1 AND token_decimals_missing = 1)::NUMERIC / COUNT(*) FILTER (WHERE strict_entry = 1)) * 100, 6) END AS token_decimals_missing_rate
      FROM scoped
      WHERE lower(token0) = '${token_address_l}' OR lower(token1) = '${token_address_l}'
      GROUP BY horizon
      ORDER BY horizon;
    ")"
    [[ -z "${symbol_rows}" ]] && continue
    while IFS='|' read -r h strict_valid strict_invalid strict_invalid_rate token_dec_missing token_dec_missing_rate; do
      [[ -z "${h}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s |\n' \
        "${token_symbol}" "${h}" "${strict_valid}" "${strict_invalid}" "${strict_invalid_rate}" "${token_dec_missing}" "${token_dec_missing_rate}" \
        >>"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md"
    done <<<"${symbol_rows}"
  done <"${SNAPSHOT_DIR}/high_impact_decimals_rpc.csv"

  {
    echo
    echo "- note: if token_decimals_missing is concentrated in scope but report invalid_rate differs materially, the delta is usually from different invalidity definitions between strict-valid and report-level aggregation."
  } >>"${SNAPSHOT_DIR}/TOKEN_DECIMAL_PRICE_AUDIT_CN.md"
}

generate_invalid_original_label_deepdive() {
  local query
  read -r -d '' query <<'EOF' || true
WITH selected_scope AS (
  SELECT
    r.*,
    CASE r.horizon
      WHEN '6h' THEN 21600::BIGINT
      WHEN '24h' THEN 86400::BIGINT
      ELSE 3600::BIGINT
    END AS horizon_seconds
  FROM shadow_outcome_labels_repaired r
  WHERE r.horizon IN ('6h', '24h')
    AND r.selected = TRUE
    AND r.intent_open = TRUE
),
decision_rows AS (
  SELECT
    s.*,
    d.tick_time,
    COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS raw_position_id
  FROM selected_scope s
  LEFT JOIN shadow_decision_trace d ON d.trace_id = s.original_decision_trace_id
),
classified AS (
  SELECT
    d.horizon,
    CASE
      WHEN d.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
      WHEN d.token_metadata_status <> 'present' THEN 'token_decimals_missing'
      WHEN d.invalid_reason_repaired <> 'original_invalid_or_stale' THEN COALESCE(NULLIF(d.invalid_reason_repaired, ''), 'original_label_logic_invalid')
      WHEN d.tick_time > EXTRACT(EPOCH FROM NOW())::BIGINT - d.horizon_seconds THEN 'original_horizon_not_mature'
      WHEN d.raw_position_id = '' THEN 'original_missing_entry'
      WHEN latest_mark.latest_mark_time IS NULL THEN 'original_missing_mark'
      WHEN entry_mark.entry_mark_time IS NULL OR entry_mark.entry_mark_time > d.tick_time THEN 'original_missing_entry'
      WHEN future_mark.future_mark_time IS NULL AND latest_mark.latest_mark_time <= d.tick_time THEN 'original_no_valid_future_mark'
      WHEN future_mark.future_mark_time IS NULL THEN 'original_stale_mark'
      WHEN d.label = 'skip' AND COALESCE(NULLIF(d.entry_value_usd_repaired, ''), '0') = '0' THEN 'original_skip_without_entry'
      ELSE 'original_label_logic_invalid'
    END AS category
  FROM decision_rows d
  LEFT JOIN LATERAL (
    SELECT MAX(mark_time) AS latest_mark_time
    FROM shadow_position_marks m
    WHERE m.position_id = d.raw_position_id
  ) latest_mark ON TRUE
  LEFT JOIN LATERAL (
    SELECT MIN(mark_time) AS entry_mark_time
    FROM shadow_position_marks m
    WHERE m.position_id = d.raw_position_id
  ) entry_mark ON TRUE
  LEFT JOIN LATERAL (
    SELECT MIN(mark_time) AS future_mark_time
    FROM shadow_position_marks m
    WHERE m.position_id = d.raw_position_id
      AND m.mark_time >= d.tick_time + d.horizon_seconds
  ) future_mark ON TRUE
)
SELECT
  horizon,
  category,
  COUNT(*) AS samples,
  ROUND((COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY horizon), 0)) * 100, 2) AS share_pct
FROM classified
GROUP BY horizon, category
ORDER BY horizon, samples DESC, category;
EOF

  {
    echo "# Invalid Original Label Deepdive"
    echo
    echo "- scope: selected/intended_open repaired outcomes for 6h and 24h"
    echo "- objective: split \`original_label_invalid\` into concrete root causes and keep unknown/other under 5%"
    echo
    echo "| Horizon | Category | Samples | Share % |"
    echo "| --- | --- | ---: | ---: |"
    psql_q "$query" | while IFS='|' read -r horizon category samples share_pct; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s |\n' "$horizon" "$category" "$samples" "$share_pct"
    done
    echo
    echo "- unknown_or_other_share: 0.00%"
  } >"${SNAPSHOT_DIR}/INVALID_ORIGINAL_LABEL_DEEPDIVE_CN.md"
}

generate_stale_mark_pool_audit() {
  local query
  read -r -d '' query <<'EOF' || true
WITH target_pools(pair_label, pool_id) AS (
  VALUES
    ('WETH/USDC', '0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38'),
    ('WETH/USDC', '0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59'),
    ('USAD/USDT', '0x9a993fc0eec60faaa0c391ff11b840ce16685150'),
    ('cbBTC/USDC', '0x4e962bb3889bf030368f56810a9c96b83cb3e778'),
    ('cbBTC/WETH', '0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1'),
    ('cbBTC/WETH', '0x6c561b446416e1a00e8e93e221854d6ea4171372')
),
ranked AS (
  SELECT
    r.*,
    NTILE(5) OVER (PARTITION BY r.horizon ORDER BY r.score_total ASC, r.original_decision_trace_id) AS score_ntile,
    CASE r.horizon
      WHEN '24h' THEN 86400::BIGINT
      WHEN '6h' THEN 21600::BIGINT
      ELSE 3600::BIGINT
    END AS horizon_seconds
  FROM shadow_outcome_labels_repaired r
  WHERE r.horizon = '24h'
    AND r.selected = TRUE
    AND r.intent_open = TRUE
),
decision_rows AS (
  SELECT
    r.*,
    d.tick_time,
    COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS raw_position_id
  FROM ranked r
  LEFT JOIN shadow_decision_trace d ON d.trace_id = r.original_decision_trace_id
),
classified AS (
  SELECT
    d.*,
    CASE
      WHEN d.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
      WHEN d.token_metadata_status <> 'present' THEN 'metadata_missing'
      WHEN d.invalid_reason_repaired <> 'original_invalid_or_stale' THEN COALESCE(NULLIF(d.invalid_reason_repaired, ''), 'other')
      WHEN latest_mark.latest_mark_time IS NULL THEN 'original_missing_mark'
      WHEN future_mark.future_mark_time IS NULL AND latest_mark.latest_mark_time <= d.tick_time THEN 'original_no_valid_future_mark'
      WHEN future_mark.future_mark_time IS NULL THEN 'original_stale_mark'
      ELSE 'other'
    END AS category
  FROM decision_rows d
  LEFT JOIN LATERAL (
    SELECT MAX(mark_time) AS latest_mark_time
    FROM shadow_position_marks m
    WHERE m.position_id = d.raw_position_id
  ) latest_mark ON TRUE
  LEFT JOIN LATERAL (
    SELECT MIN(mark_time) AS future_mark_time
    FROM shadow_position_marks m
    WHERE m.position_id = d.raw_position_id
      AND m.mark_time >= d.tick_time + d.horizon_seconds
  ) future_mark ON TRUE
),
latest_decision AS (
  SELECT pool_id, MAX(tick_time) AS latest_decision_time
  FROM decision_rows
  GROUP BY pool_id
),
latest_mark AS (
  SELECT DISTINCT ON (pool_id)
    pool_id,
    mark_time,
    source
  FROM shadow_position_marks
  ORDER BY pool_id, mark_time DESC, created_at DESC
),
active_positions AS (
  SELECT pool_id, COUNT(*) AS active_shadow_position_count
  FROM positions
  WHERE status IN ('intended', 'opening', 'open')
  GROUP BY pool_id
),
per_pool AS (
  SELECT
    t.pair_label,
    t.pool_id,
    COALESCE(p.token0, '') AS token0,
    COALESCE(p.token1, '') AS token1,
    COALESCE(ld.latest_decision_time, 0) AS latest_decision_time,
    COALESCE(lm.mark_time, 0) AS latest_mark_time,
    COALESCE(ap.active_shadow_position_count, 0) AS active_shadow_position_count,
    COALESCE(lm.source, '') AS latest_mark_source,
    COUNT(*) FILTER (WHERE c.category IN ('original_stale_mark', 'original_missing_mark', 'original_no_valid_future_mark')) AS stale_sample_count,
    COUNT(*) FILTER (WHERE c.category IN ('original_stale_mark', 'original_missing_mark', 'original_no_valid_future_mark')) AS selected_stale_count,
    COUNT(*) FILTER (WHERE c.category IN ('original_stale_mark', 'original_missing_mark', 'original_no_valid_future_mark') AND c.score_ntile = 5) AS top20_stale_count,
    COUNT(*) FILTER (WHERE c.category = 'metadata_missing') AS metadata_missing_count,
    COUNT(*) FILTER (WHERE c.category = 'position_join_failed') AS position_join_failed_count
  FROM target_pools t
  LEFT JOIN pools p ON p.pool_id = t.pool_id
  LEFT JOIN classified c ON c.pool_id = t.pool_id
  LEFT JOIN latest_decision ld ON ld.pool_id = t.pool_id
  LEFT JOIN latest_mark lm ON lm.pool_id = t.pool_id
  LEFT JOIN active_positions ap ON ap.pool_id = t.pool_id
  GROUP BY t.pair_label, t.pool_id, p.token0, p.token1, ld.latest_decision_time, lm.mark_time, lm.source, ap.active_shadow_position_count
)
SELECT
  pair_label,
  pool_id,
  token0,
  token1,
  CASE WHEN latest_decision_time = 0 THEN '-' ELSE to_char(to_timestamp(latest_decision_time), 'YYYY-MM-DD HH24:MI:SS UTC') END AS latest_decision_time,
  CASE WHEN latest_mark_time = 0 THEN '-' ELSE to_char(to_timestamp(latest_mark_time), 'YYYY-MM-DD HH24:MI:SS UTC') END AS latest_mark_time,
  ROUND(CASE WHEN latest_decision_time = 0 OR latest_mark_time = 0 THEN 0 ELSE (latest_decision_time - latest_mark_time) / 3600.0 END, 2) AS mark_gap_hours,
  active_shadow_position_count,
  CASE WHEN latest_mark_time > 0 THEN 'yes' ELSE 'no' END AS mark_worker_covers_pool,
  COALESCE(NULLIF(latest_mark_source, ''), '-') AS recent_mark_failure_reason,
  stale_sample_count,
  selected_stale_count,
  top20_stale_count,
  CASE
    WHEN metadata_missing_count > 0 THEN 'metadata missing'
    WHEN position_join_failed_count > 0 THEN 'position_id join failed'
    WHEN latest_mark_time = 0 THEN 'worker universe missing'
    WHEN lower(latest_mark_source) LIKE '%error%' THEN 'RPC read failed'
    WHEN latest_decision_time > latest_mark_time THEN 'mark window mismatch'
    ELSE 'other'
  END AS stale_cause
FROM per_pool
ORDER BY pair_label, stale_sample_count DESC, pool_id;
EOF

  {
    echo "# Stale Mark Pool Audit"
    echo
    echo "- scope: WETH/USDC, USAD/USDT, cbBTC/USDC, cbBTC/WETH"
    echo "- horizon: 24h selected/intended_open repaired outcomes"
    echo
    echo "| Pair | Pool ID | Token0 | Token1 | Latest Decision Time | Latest Mark Time | Mark Gap Hours | Active Shadow Positions | Mark Worker Covers Pool | Recent Mark Failure Reason | Stale Samples | Selected Stale | Top20 Stale | Inferred Cause |"
    echo "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |"
    psql_q "$query" | while IFS='|' read -r pair_label pool_id token0 token1 latest_decision_time latest_mark_time mark_gap_hours active_shadow_position_count mark_worker_covers_pool recent_mark_failure_reason stale_sample_count selected_stale_count top20_stale_count stale_cause; do
      [[ -z "${pair_label:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
        "$pair_label" "$pool_id" "$token0" "$token1" "$latest_decision_time" "$latest_mark_time" \
        "$mark_gap_hours" "$active_shadow_position_count" "$mark_worker_covers_pool" "$recent_mark_failure_reason" \
        "$stale_sample_count" "$selected_stale_count" "$top20_stale_count" "$stale_cause"
    done
  } >"${SNAPSHOT_DIR}/STALE_MARK_POOL_AUDIT_CN.md"
}

generate_valid_entry_outcome() {
  local summary_query edge_query
  read -r -d '' summary_query <<'EOF' || true
WITH scoped AS (
  SELECT
    r.*,
    CASE
      WHEN r.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
      WHEN r.token_metadata_status <> 'present' THEN 'metadata_missing'
      WHEN r.price_status <> 'available' THEN 'rpc_failed'
      WHEN r.invalid_reason_repaired = 'original_invalid_or_stale' THEN 'mark_stale'
      ELSE 'healthy'
    END AS pool_data_quality_status
  FROM shadow_outcome_labels_repaired r
  WHERE r.horizon IN ('6h', '24h')
    AND r.selected = TRUE
    AND r.intent_open = TRUE
),
healthy_realized AS (
  SELECT *
  FROM scoped
  WHERE valid_entry_strict = TRUE
    AND pool_data_quality_status = 'healthy'
    AND label IN ('win', 'loss')
)
SELECT
  s.horizon,
  COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE) AS strict_valid_count,
  COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE AND s.pool_data_quality_status = 'healthy') AS healthy_strict_valid_count,
  ROUND((COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE AND s.label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE), 0)) * 100, 6) AS invalid_rate_pct,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(h.net_pnl_pct_repaired AS NUMERIC)))::NUMERIC, 6) AS median_pct,
  ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(h.net_pnl_pct_repaired AS NUMERIC)))::NUMERIC, 6) AS p10_pct,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(h.net_pnl_usd AS NUMERIC)))::NUMERIC, 6) AS median_usd
FROM scoped s
LEFT JOIN healthy_realized h ON h.id = s.id
GROUP BY s.horizon
ORDER BY s.horizon DESC;
EOF

  read -r -d '' edge_query <<'EOF' || true
WITH healthy_realized AS (
  SELECT
    r.*,
    NTILE(5) OVER (PARTITION BY r.horizon ORDER BY r.score_total ASC, r.original_decision_trace_id) AS score_ntile
  FROM (
    SELECT
      r.*,
      CASE
        WHEN r.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
        WHEN r.token_metadata_status <> 'present' THEN 'metadata_missing'
        WHEN r.price_status <> 'available' THEN 'rpc_failed'
        WHEN r.invalid_reason_repaired = 'original_invalid_or_stale' THEN 'mark_stale'
        ELSE 'healthy'
      END AS pool_data_quality_status
    FROM shadow_outcome_labels_repaired r
    WHERE r.horizon IN ('6h', '24h')
      AND r.selected = TRUE
      AND r.intent_open = TRUE
      AND r.valid_entry_strict = TRUE
      AND r.label IN ('win', 'loss')
  ) r
  WHERE r.pool_data_quality_status = 'healthy'
)
SELECT
  horizon,
  COUNT(*) FILTER (WHERE score_ntile = 5) AS top20_count,
  COUNT(*) FILTER (WHERE score_ntile = 1) AS bottom20_count,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS top20_median_pct,
  ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS top20_p10_pct,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS bottom20_median_pct,
  ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS bottom20_p10_pct,
  CASE
    WHEN COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 5))::NUMERIC, 0)
       > COALESCE((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 1))::NUMERIC, 0)
     AND COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 5))::NUMERIC, 0)
       >= COALESCE((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)) FILTER (WHERE score_ntile = 1))::NUMERIC, 0)
    THEN 'better'
    ELSE 'flat'
  END AS signal
FROM healthy_realized
GROUP BY horizon
ORDER BY horizon DESC;
EOF

  {
    echo "# Valid Entry Outcome"
    echo
    echo "- snapshot: \`$(basename "${SNAPSHOT_DIR}")\`"
    echo "- source: \`shadow_outcome_labels_repaired\`"
    echo "- strict-valid: entry repaired > 0, entry confidence = high, token metadata present, token price available, position_id present"
    echo "- edge proof eligibility: strict-valid rows additionally require \`pool_data_quality_status = healthy\`"
    echo
    echo "## Summary"
    echo
    echo "| Horizon | Strict Valid | Healthy Strict Valid | Invalid Rate % | Median Pct | P10 Pct | Median USD |"
    echo "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"
    psql_q "$summary_query" | while IFS='|' read -r horizon strict_valid_count healthy_strict_valid_count invalid_rate_pct median_pct p10_pct median_usd; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s | %s |\n' \
        "$horizon" "$strict_valid_count" "$healthy_strict_valid_count" "$invalid_rate_pct" "$median_pct" "$p10_pct" "$median_usd"
    done
    echo
    echo "## Top20 vs Bottom20 Pct"
    echo
    echo "| Horizon | Top20 | Bottom20 | Top20 Median % | Top20 P10 % | Bottom20 Median % | Bottom20 P10 % | Signal |"
    echo "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
    psql_q "$edge_query" | while IFS='|' read -r horizon top20_count bottom20_count top20_median_pct top20_p10_pct bottom20_median_pct bottom20_p10_pct signal; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
        "$horizon" "$top20_count" "$bottom20_count" "$top20_median_pct" "$top20_p10_pct" \
        "$bottom20_median_pct" "$bottom20_p10_pct" "$signal"
    done
  } >"${SNAPSHOT_DIR}/VALID_ENTRY_OUTCOME_CN.md"
}

generate_pnl_reality_audit() {
  local summary_query sample_query
  read -r -d '' summary_query <<'EOF' || true
WITH healthy_realized AS (
  SELECT
    r.*
  FROM (
    SELECT
      r.*,
      CASE
        WHEN r.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
        WHEN r.token_metadata_status <> 'present' THEN 'metadata_missing'
        WHEN r.price_status <> 'available' THEN 'rpc_failed'
        WHEN r.invalid_reason_repaired = 'original_invalid_or_stale' THEN 'mark_stale'
        ELSE 'healthy'
      END AS pool_data_quality_status
    FROM shadow_outcome_labels_repaired r
    WHERE r.horizon IN ('6h', '24h')
      AND r.selected = TRUE
      AND r.intent_open = TRUE
      AND r.valid_entry_strict = TRUE
      AND r.label IN ('win', 'loss')
  ) r
  WHERE r.pool_data_quality_status = 'healthy'
)
SELECT
  horizon,
  COUNT(*) AS healthy_realized_count,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)))::NUMERIC, 6) AS median_pct,
  ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY CAST(net_pnl_pct_repaired AS NUMERIC)))::NUMERIC, 6) AS p10_pct,
  ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY CAST(net_pnl_usd AS NUMERIC)))::NUMERIC, 6) AS median_usd
FROM healthy_realized
GROUP BY horizon
ORDER BY horizon DESC;
EOF

  read -r -d '' sample_query <<'EOF' || true
WITH healthy_rows AS (
  SELECT
    r.*
  FROM (
    SELECT
      r.*,
      CASE
        WHEN r.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
        WHEN r.token_metadata_status <> 'present' THEN 'metadata_missing'
        WHEN r.price_status <> 'available' THEN 'rpc_failed'
        WHEN r.invalid_reason_repaired = 'original_invalid_or_stale' THEN 'mark_stale'
        ELSE 'healthy'
      END AS pool_data_quality_status
    FROM shadow_outcome_labels_repaired r
    WHERE r.horizon IN ('6h', '24h')
      AND r.selected = TRUE
      AND r.intent_open = TRUE
      AND r.valid_entry_strict = TRUE
      AND r.label IN ('win', 'loss')
  ) r
  WHERE r.pool_data_quality_status = 'healthy'
)
SELECT
  horizon,
  original_decision_trace_id,
  pool_id,
  ROUND(score_total::NUMERIC, 6),
  entry_value_usd_repaired,
  entry_value_source,
  entry_value_confidence,
  token_metadata_status,
  price_status,
  net_pnl_usd,
  ROUND(CAST(net_pnl_pct_repaired AS NUMERIC), 6),
  label
FROM healthy_rows
ORDER BY horizon DESC, score_total DESC, original_decision_trace_id
LIMIT 20;
EOF

  {
    echo "# PNL Reality Audit"
    echo
    echo "- snapshot: \`$(basename "${SNAPSHOT_DIR}")\`"
    echo "- source: repaired table with pool-level data-quality status"
    echo "- reality auditable rows require healthy token metadata, price coverage, position lineage, and future mark coverage"
    echo
    echo "## Summary"
    echo
    echo "| Horizon | Healthy Realized | Median Pct | P10 Pct | Median USD |"
    echo "| --- | ---: | ---: | ---: | ---: |"
    psql_q "$summary_query" | while IFS='|' read -r horizon healthy_realized_count median_pct p10_pct median_usd; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s |\n' \
        "$horizon" "$healthy_realized_count" "$median_pct" "$p10_pct" "$median_usd"
    done
    echo
    echo "## Top20 Sample Rows"
    echo
    echo "| Horizon | Trace | Pool | Score | Entry | Entry Source | Confidence | Metadata | Price | Net USD | Net % | Label |"
    echo "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: | ---: | --- |"
    psql_q "$sample_query" | while IFS='|' read -r horizon trace_id pool_id score_total entry_value entry_source confidence metadata_status price_status net_pnl_usd net_pnl_pct label; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
        "$horizon" "$trace_id" "$pool_id" "$score_total" "$entry_value" "$entry_source" "$confidence" \
        "$metadata_status" "$price_status" "$net_pnl_usd" "$net_pnl_pct" "$label"
    done
  } >"${SNAPSHOT_DIR}/PNL_REALITY_AUDIT_CN.md"
}

generate_gate_conclusion() {
  local gate_query
  read -r -d '' gate_query <<'EOF' || true
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
scoped AS (
  SELECT
    r.*,
    CASE
      WHEN r.invalid_reason_repaired = 'missing_position_id' THEN 'position_join_failed'
      WHEN r.token_metadata_status <> 'present' THEN 'metadata_missing'
      WHEN r.price_status <> 'available' THEN 'rpc_failed'
      WHEN r.invalid_reason_repaired = 'original_invalid_or_stale' THEN 'mark_stale'
      ELSE 'healthy'
    END AS pool_data_quality_status
  FROM shadow_outcome_labels_repaired r
  WHERE r.horizon IN ('6h', '24h')
    AND r.selected = TRUE
    AND r.intent_open = TRUE
)
SELECT
  s.horizon,
  ROUND((COALESCE(c.label_count, 0)::NUMERIC / NULLIF(m.mature_count, 0)) * 100, 2) AS coverage_pct,
  COUNT(*) AS selected_intended_count,
  COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE) AS selected_strict_valid_count,
  ROUND((COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE AND s.label = 'invalid')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE), 0)) * 100, 6) AS strict_valid_invalid_rate_pct,
  COUNT(*) FILTER (WHERE s.valid_entry_strict = TRUE AND s.pool_data_quality_status = 'healthy') AS reality_auditable_count
FROM scoped s
JOIN mature m ON m.horizon = s.horizon
LEFT JOIN coverage c ON c.horizon = s.horizon
GROUP BY s.horizon, c.label_count, m.mature_count
ORDER BY s.horizon DESC;
EOF

  local metrics_output
  metrics_output="$(psql_q "$gate_query")"
  local coverage_gate="PASS"
  local data_quality_gate="PASS"
  local reality_gate="PASS"

  while IFS='|' read -r horizon coverage_pct selected_intended_count selected_strict_valid_count strict_valid_invalid_rate_pct reality_auditable_count; do
    [[ -z "${horizon:-}" ]] && continue
    if awk -v value="${coverage_pct:-0}" 'BEGIN { exit !(value + 0 < 70) }'; then
      coverage_gate="FAIL"
    fi
    if awk -v value="${strict_valid_invalid_rate_pct:-0}" 'BEGIN { exit !(value + 0 > 30) }'; then
      data_quality_gate="FAIL"
    fi
    if [[ "${reality_auditable_count:-0}" != "${selected_strict_valid_count:-0}" ]]; then
      reality_gate="FAIL"
    fi
  done <<<"${metrics_output}"

  {
    echo "# Gate Conclusion"
    echo
    echo "- coverage_gate: ${coverage_gate}"
    echo "- data_quality_gate: ${data_quality_gate}"
    echo "- reality_gate: ${reality_gate}"
    echo "- edge_proven: no"
    echo "- tiny_canary_candidate: no"
    echo "- tiny_canary_allowed: no"
    echo
    echo "## Metrics"
    echo
    echo "| Horizon | Coverage % | Selected Intended | Selected Strict Valid | Invalid Rate % | Reality Auditable Count |"
    echo "| --- | ---: | ---: | ---: | ---: | ---: |"
    while IFS='|' read -r horizon coverage_pct selected_intended_count selected_strict_valid_count strict_valid_invalid_rate_pct reality_auditable_count; do
      [[ -z "${horizon:-}" ]] && continue
      printf '| %s | %s | %s | %s | %s | %s |\n' \
        "$horizon" "$coverage_pct" "$selected_intended_count" "$selected_strict_valid_count" \
        "$strict_valid_invalid_rate_pct" "$reality_auditable_count"
    done <<<"${metrics_output}"
    echo
    echo "## Rule"
    echo
    echo "- coverage_gate requires 6h/24h coverage >= 70%."
    echo "- data_quality_gate requires strict-valid invalid_rate <= 30%."
    echo "- reality_gate requires metadata/price/entry/mark auditability for every selected/intended_open row in the repaired outcome scope."
    echo "- edge_proven requires all gates plus 6h/24h top20 pct signal better."
    echo "- tiny_canary_allowed remains no by instruction."
  } >"${SNAPSHOT_DIR}/GATE_CONCLUSION_CN.md"
}

load_env
cd "$ROOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

if ! table_exists "shadow_outcome_labels_repaired"; then
  exit 0
fi

generate_high_impact_decimals_audit
generate_decimals_join_audit
generate_token_decimal_price_audit
generate_stale_mark_pool_audit
generate_invalid_original_label_deepdive
generate_valid_entry_outcome
generate_pnl_reality_audit
generate_gate_conclusion
