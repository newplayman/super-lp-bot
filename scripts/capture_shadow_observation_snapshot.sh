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
- [outcome_counts.csv](${SNAPSHOT_DIR}/outcome_counts.csv)
- [bucket_stats.csv](${SNAPSHOT_DIR}/bucket_stats.csv)
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
write_summary "$readiness_status" "$backfill_status" "$report_status"

printf '[shadow-observation] dir=%s readiness=%s backfill=%s report=%s\n' \
  "$SNAPSHOT_DIR" "$readiness_status" "$backfill_status" "$report_status"
