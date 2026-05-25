#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_BASE_DIR="${LPBOT_SHADOW_OBS_REPORT_BASE_DIR:-reports/shadow_outcomes}"
TIMESTAMP_UTC="$(date -u +%Y%m%d_%H%M)"
SNAPSHOT_DIR="${LPBOT_SHADOW_OBS_SNAPSHOT_DIR:-${REPORT_BASE_DIR}/${TIMESTAMP_UTC}}"
CONFIG_PATH="${LPBOT_SHADOW_OBS_CONFIG:-configs/config.shadow.research.toml}"
BACKFILL_TIMEOUT_SECONDS="${LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS:-900}"

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then set -a; . ./.env.postgres; set +a; fi
  if [[ -f ./.env.redis ]]; then set -a; . ./.env.redis; set +a; fi
  if [[ -f ./.env.shadow ]]; then set -a; . ./.env.shadow; set +a; fi
  if [[ -f ./.env.dashboard ]]; then set -a; . ./.env.dashboard; set +a; fi
  if [[ -f ./.env.chain ]]; then set -a; . ./.env.chain; set +a; fi
  export POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
}

write_queries() {
  cat >"${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" <<'EOF'
-- outcome_counts.csv
SELECT
  horizon,
  label,
  COUNT(*) AS samples
FROM shadow_outcome_labels
GROUP BY horizon, label
ORDER BY horizon, label;

-- bucket_stats.csv
WITH base_rows AS (
  SELECT
    o.horizon,
    o.label,
    o.selected,
    o.score_total,
    CAST(o.simulated_net_pnl_usd AS NUMERIC) AS net_pnl_usd,
    COALESCE(p.fee_bps, 0) AS fee_bps,
    CAST(COALESCE(p.tvl_usd, '0') AS NUMERIC) AS tvl_usd,
    COALESCE((d.score_json::jsonb ->> 'volatility_score')::NUMERIC, 0) AS volatility_score
  FROM shadow_outcome_labels o
  LEFT JOIN (
    SELECT pool_id,
           MAX(fee_bps) AS fee_bps,
           MAX(COALESCE(tvl_usd, '0')) AS tvl_usd
    FROM pools
    GROUP BY pool_id
  ) p ON p.pool_id = o.pool_id
  LEFT JOIN shadow_decision_trace d ON d.trace_id = o.decision_trace_id
),
bucketed AS (
  SELECT
    'score'::TEXT AS bucket_family,
    horizon,
    CASE
      WHEN score_total >= 80 THEN '80+'
      WHEN score_total >= 70 THEN '70-79'
      WHEN score_total >= 60 THEN '60-69'
      ELSE '<60'
    END AS bucket_name,
    label,
    net_pnl_usd
  FROM base_rows
  UNION ALL
  SELECT
    'tvl'::TEXT AS bucket_family,
    horizon,
    CASE
      WHEN tvl_usd >= 1000000 THEN '>=1m'
      WHEN tvl_usd >= 250000 THEN '250k-1m'
      WHEN tvl_usd >= 50000 THEN '50k-250k'
      ELSE '<50k'
    END AS bucket_name,
    label,
    net_pnl_usd
  FROM base_rows
  UNION ALL
  SELECT
    'fee_tier'::TEXT AS bucket_family,
    horizon,
    CASE
      WHEN fee_bps <= 5 THEN '<=5 bps'
      WHEN fee_bps <= 25 THEN '25 bps'
      ELSE fee_bps::TEXT || ' bps'
    END AS bucket_name,
    label,
    net_pnl_usd
  FROM base_rows
  UNION ALL
  SELECT
    'volatility'::TEXT AS bucket_family,
    horizon,
    CASE
      WHEN volatility_score >= 80 THEN '80+'
      WHEN volatility_score >= 40 THEN '40-79'
      ELSE '<40'
    END AS bucket_name,
    label,
    net_pnl_usd
  FROM base_rows
)
SELECT
  bucket_family,
  horizon,
  bucket_name,
  COUNT(*) AS samples,
  COALESCE(SUM(CASE WHEN label = 'win' THEN 1 ELSE 0 END), 0) AS wins,
  COALESCE(SUM(CASE WHEN label = 'loss' THEN 1 ELSE 0 END), 0) AS losses,
  COALESCE(SUM(CASE WHEN label = 'invalid' THEN 1 ELSE 0 END), 0) AS invalids,
  ROUND(
    COALESCE(SUM(CASE WHEN label = 'win' THEN 1 ELSE 0 END)::NUMERIC /
    NULLIF(SUM(CASE WHEN label IN ('win', 'loss') THEN 1 ELSE 0 END), 0), 0),
    6
  ) AS win_rate,
  ROUND((AVG(net_pnl_usd) FILTER (WHERE label IN ('win', 'loss')))::NUMERIC, 6) AS avg_net_pnl_usd,
  ROUND(
    (
      percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd)
      FILTER (WHERE label IN ('win', 'loss'))
    )::NUMERIC,
    6
  ) AS median_net_pnl_usd
FROM bucketed
GROUP BY bucket_family, horizon, bucket_name
ORDER BY bucket_family, horizon, bucket_name;

-- high_low_score_diagnostics.csv
WITH scored AS (
  SELECT
    horizon,
    score_total,
    label,
    CAST(simulated_net_pnl_usd AS NUMERIC) AS net_pnl_usd
  FROM shadow_outcome_labels
),
agg AS (
  SELECT
    horizon,
    COUNT(*) FILTER (WHERE score_total >= 80) AS high_score_count,
    COUNT(*) FILTER (WHERE score_total < 70) AS low_score_count,
    COUNT(*) FILTER (WHERE score_total >= 80 AND label IN ('win', 'loss')) AS high_score_realized_count,
    COUNT(*) FILTER (WHERE score_total < 70 AND label IN ('win', 'loss')) AS low_score_realized_count,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_total >= 80 AND label IN ('win', 'loss')))::NUMERIC, 6) AS high_score_avg_net_pnl_usd,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_total < 70 AND label IN ('win', 'loss')))::NUMERIC, 6) AS low_score_avg_net_pnl_usd,
    ROUND((
      percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd)
      FILTER (WHERE score_total >= 80 AND label IN ('win', 'loss'))
    )::NUMERIC, 6) AS high_score_median_net_pnl_usd,
    ROUND((
      percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd)
      FILTER (WHERE score_total < 70 AND label IN ('win', 'loss'))
    )::NUMERIC, 6) AS low_score_median_net_pnl_usd
  FROM scored
  GROUP BY horizon
)
SELECT
  horizon,
  COALESCE(high_score_count, 0) AS high_score_count,
  COALESCE(low_score_count, 0) AS low_score_count,
  COALESCE(high_score_realized_count, 0) AS high_score_realized_count,
  COALESCE(low_score_realized_count, 0) AS low_score_realized_count,
  COALESCE(high_score_avg_net_pnl_usd, 0) AS high_score_avg_net_pnl_usd,
  COALESCE(high_score_median_net_pnl_usd, 0) AS high_score_median_net_pnl_usd,
  COALESCE(low_score_avg_net_pnl_usd, 0) AS low_score_avg_net_pnl_usd,
  COALESCE(low_score_median_net_pnl_usd, 0) AS low_score_median_net_pnl_usd,
  CASE
    WHEN COALESCE(high_score_count, 0) = 0 THEN 'high_score_count=0'
    WHEN COALESCE(high_score_realized_count, 0) = 0 THEN 'high_score_realized_count=0'
    WHEN COALESCE(low_score_count, 0) = 0 THEN 'low_score_count=0'
    WHEN COALESCE(low_score_realized_count, 0) = 0 THEN 'low_score_realized_count=0'
    ELSE ''
  END AS insufficient_reason
FROM agg
ORDER BY horizon;

-- invalid_reason_counts.csv
WITH horizons AS (
  SELECT '1h'::TEXT AS horizon, 3600::BIGINT AS horizon_seconds
  UNION ALL SELECT '6h'::TEXT, 21600::BIGINT
  UNION ALL SELECT '24h'::TEXT, 86400::BIGINT
),
eligible AS (
  SELECT
    h.horizon,
    h.horizon_seconds,
    d.trace_id,
    d.pool_id,
    d.chain,
    d.tick_time,
    COALESCE(NULLIF(BTRIM(d.position_id), ''), '') AS position_id
  FROM shadow_decision_trace d
  CROSS JOIN horizons h
  WHERE d.selected = TRUE
    AND d.intent_open = TRUE
    AND d.final_action IN ('open_shadow_position', 'reuse_shadow_position')
),
latest_marks AS (
  SELECT position_id, MAX(mark_time) AS latest_mark_time
  FROM shadow_position_marks
  GROUP BY position_id
),
classified AS (
  SELECT
    e.horizon,
    CASE
      WHEN e.tick_time > EXTRACT(EPOCH FROM NOW())::BIGINT - e.horizon_seconds THEN 'horizon not mature'
      WHEN e.position_id = '' THEN 'other'
      WHEN p.pool_id IS NULL THEN 'missing pool metadata'
      WHEN e.chain = 'base' AND e.pool_id !~* '^0x[0-9a-f]{40}$' THEN 'missing gas estimate'
      WHEN lm.latest_mark_time IS NULL THEN 'missing mark'
      WHEN lm.latest_mark_time < e.tick_time + e.horizon_seconds THEN 'stale mark'
      ELSE 'other'
    END AS invalid_reason
  FROM eligible e
  LEFT JOIN pools p ON p.pool_id = e.pool_id
  LEFT JOIN latest_marks lm ON lm.position_id = e.position_id
)
SELECT
  horizon,
  invalid_reason,
  COUNT(*) AS samples
FROM classified
GROUP BY horizon, invalid_reason
ORDER BY horizon, invalid_reason;
EOF
}

run_query_to_csv() {
  local sql_file="$1"
  local sql_marker="$2"
  local output_csv="$3"
  awk -v marker="$sql_marker" '
    $0 == marker {capture=1; next}
    /^-- / && capture {exit}
    capture {print}
  ' "$sql_file" | psql "$POSTGRES_DSN" -X -A -F, -P pager=off -f - >"$output_csv"
}

generate_trend_summary() {
  local trend_tsv="${SNAPSHOT_DIR}/trend_metrics.tsv"
  local generated_at
  generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  : >"$trend_tsv"

  shopt -s nullglob
  local report
  for report in "$REPORT_BASE_DIR"/*/REPORT_SHADOW_OUTCOMES_CN.md; do
    local snapshot
    snapshot="$(basename "$(dirname "$report")")"
    awk -v snap="$snapshot" '
      function trim(val) {
        gsub(/^[ \t]+|[ \t]+$/, "", val)
        return val
      }
      function emit() {
        if (h != "") {
          print snap "\t" h "\t" samples "\t" selected "\t" realized "\t" invalid_rate "\t" median "\t" p10 "\t" gas_rate "\t" high_low
        }
      }
      /^## / {
        if (h != "") emit()
        h = $2
        samples = selected = realized = invalid_rate = median = p10 = gas_rate = high_low = ""
        next
      }
      /^- 样本数: / { sub(/^- 样本数: /, "", $0); samples = trim($0); next }
      /^- selected_sample_count: / { sub(/^- selected_sample_count: /, "", $0); selected = trim($0); next }
      /^- realized_sample_count: / { sub(/^- realized_sample_count: /, "", $0); realized = trim($0); next }
      /^- invalid_rate: / { sub(/^- invalid_rate: /, "", $0); sub(/%$/, "", $0); invalid_rate = trim($0); next }
      /^- 中位数净收益: / { sub(/^- 中位数净收益: /, "", $0); sub(/ USD$/, "", $0); median = trim($0); next }
      /^- P10 \/ P90: / {
        sub(/^- P10 \/ P90: /, "", $0)
        split($0, parts, " / ")
        p10 = trim(parts[1])
        next
      }
      /^- gas_adjusted_positive_rate: / { sub(/^- gas_adjusted_positive_rate: /, "", $0); sub(/%$/, "", $0); gas_rate = trim($0); next }
      /^- high_score_vs_low_score: / {
        sub(/^- high_score_vs_low_score: /, "", $0)
        split($0, parts, " ")
        high_low = trim(parts[1])
        next
      }
      END {
        if (h != "") emit()
      }
    ' "$report" >>"$trend_tsv"
  done
  shopt -u nullglob

  awk -F '\t' -v generated_at="$generated_at" '
    BEGIN {
      print "# Trend Summary"
      print ""
      print "- 生成时间: " generated_at
      print "- 来源目录: reports/shadow_outcomes/*"
      print ""
    }
    {
      rows[$2] = rows[$2] sprintf("| %s | %s | %s | %s | %s%% | %s | %s | %s%% | %s |\n", $1, $3, $4, $5, $6, $7, $8, $9, $10)
      seen[$2] = 1
    }
    END {
      split("1h 6h 24h", order, " ")
      for (i = 1; i <= 3; i++) {
        h = order[i]
        print "## " h
        print ""
        print "| Snapshot | Samples | Selected | Realized | Invalid Rate | Median | P10 | Gas+ Positive | High vs Low |"
        print "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
        if (seen[h]) {
          printf "%s", rows[h]
        } else {
          print "| <none> | 0 | 0 | 0 | 0.00% | 0.000000 | 0.000000 | 0.00% | insufficient |"
        }
        print ""
      }
    }
  ' "$trend_tsv" >"${SNAPSHOT_DIR}/TREND_SUMMARY_CN.md"
}

write_summary() {
  local readiness_status="$1"
  local backfill_status="$2"
  local report_status="$3"
  local outcome_total
  outcome_total="$(psql "$POSTGRES_DSN" -X -A -t -c "SELECT COUNT(*) FROM shadow_outcome_labels;" | tr -d '[:space:]')"
  cat >"${SNAPSHOT_DIR}/OBSERVATION_SUMMARY_CN.md" <<EOF
# Observation Summary

- 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- snapshot 目录: \`${SNAPSHOT_DIR}\`
- readiness: ${readiness_status}
- backfill: ${backfill_status}
- report: ${report_status}
- shadow_outcome_labels 总样本: ${outcome_total:-0}

## 文件

- [SHADOW_RESEARCH_READINESS_CN.md](${SNAPSHOT_DIR}/SHADOW_RESEARCH_READINESS_CN.md)
- [REPORT_SHADOW_OUTCOMES_CN.md](${SNAPSHOT_DIR}/REPORT_SHADOW_OUTCOMES_CN.md)
- [TREND_SUMMARY_CN.md](${SNAPSHOT_DIR}/TREND_SUMMARY_CN.md)
- [outcome_counts.csv](${SNAPSHOT_DIR}/outcome_counts.csv)
- [bucket_stats.csv](${SNAPSHOT_DIR}/bucket_stats.csv)
- [high_low_score_diagnostics.csv](${SNAPSHOT_DIR}/high_low_score_diagnostics.csv)
- [invalid_reason_counts.csv](${SNAPSHOT_DIR}/invalid_reason_counts.csv)
- [RAW_SQL_QUERIES.sql](${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql)
EOF
}

load_env
cd "$ROOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

readiness_status="PASS"
if ! LPBOT_SHADOW_RESEARCH_REPORT_PATH="${SNAPSHOT_DIR}/SHADOW_RESEARCH_READINESS_CN.md" \
  ./scripts/shadow_research_readiness_check.sh; then
  readiness_status="FAIL"
  write_queries
  : >"${SNAPSHOT_DIR}/outcome_counts.csv"
  : >"${SNAPSHOT_DIR}/bucket_stats.csv"
  write_summary "$readiness_status" "SKIPPED" "SKIPPED"
  exit 2
fi

write_queries

backfill_status="SKIPPED"
if command -v timeout >/dev/null 2>&1; then
  if timeout --signal=TERM "${BACKFILL_TIMEOUT_SECONDS}" \
    go run -tags shadow ./cmd/lpbot \
      --config="${CONFIG_PATH}" \
      --shadow-outcomes-backfill >/dev/null 2>"${SNAPSHOT_DIR}/backfill.stderr.log"; then
    backfill_status="OK"
  else
    backfill_rc=$?
    if [[ "$backfill_rc" == "124" || "$backfill_rc" == "143" ]]; then
      backfill_status="TIMEBOXED"
    else
      backfill_status="ERROR(${backfill_rc})"
    fi
  fi
else
  backfill_status="SKIPPED(no-timeout)"
fi

report_status="OK"
if ! go run -tags shadow ./cmd/lpbot \
  --config="${CONFIG_PATH}" \
  --report-shadow-outcomes \
  --report-shadow-outcomes-path="${SNAPSHOT_DIR}/REPORT_SHADOW_OUTCOMES_CN.md" \
  >/dev/null 2>"${SNAPSHOT_DIR}/report.stderr.log"; then
  report_status="FAIL"
fi

run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- outcome_counts.csv" "${SNAPSHOT_DIR}/outcome_counts.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- bucket_stats.csv" "${SNAPSHOT_DIR}/bucket_stats.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- high_low_score_diagnostics.csv" "${SNAPSHOT_DIR}/high_low_score_diagnostics.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- invalid_reason_counts.csv" "${SNAPSHOT_DIR}/invalid_reason_counts.csv"
generate_trend_summary
write_summary "$readiness_status" "$backfill_status" "$report_status"

printf '[shadow-observation] dir=%s readiness=%s backfill=%s report=%s\n' \
  "$SNAPSHOT_DIR" "$readiness_status" "$backfill_status" "$report_status"
