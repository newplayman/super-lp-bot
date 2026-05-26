#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_BASE_DIR="${LPBOT_SHADOW_OBS_REPORT_BASE_DIR:-reports/shadow_outcomes}"
TIMESTAMP_UTC="$(date -u +%Y%m%d_%H%M)"
SNAPSHOT_DIR="${LPBOT_SHADOW_OBS_SNAPSHOT_DIR:-${REPORT_BASE_DIR}/${TIMESTAMP_UTC}}"
CONFIG_PATH="${LPBOT_SHADOW_OBS_CONFIG:-configs/config.shadow.research.toml}"
BACKFILL_TIMEOUT_SECONDS="${LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS:-900}"
BACKFILL_SEQUENCE="${LPBOT_SHADOW_OBS_BACKFILL_SEQUENCE:-24h 6h 6h 1h}"
BACKFILL_LOCK_FILE="${LPBOT_SHADOW_BACKFILL_LOCK_FILE:-/tmp/lpbot_shadow_backfill.lock}"
BACKFILL_LOCK_WAIT_SECONDS="${LPBOT_SHADOW_BACKFILL_LOCK_WAIT_SECONDS:-5}"

BEFORE_LABELS_6H=0
BEFORE_LABELS_24H=0
AFTER_LABELS_6H=0
AFTER_LABELS_24H=0
RUN_STARTED_EPOCH=0
RUN_ENDED_EPOCH=0

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
WITH horizons AS (
  SELECT '1h'::TEXT AS horizon
  UNION ALL SELECT '6h'::TEXT
  UNION ALL SELECT '24h'::TEXT
),
scored AS (
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
  h.horizon,
  COALESCE(a.high_score_count, 0) AS high_score_count,
  COALESCE(a.low_score_count, 0) AS low_score_count,
  COALESCE(a.high_score_realized_count, 0) AS high_score_realized_count,
  COALESCE(a.low_score_realized_count, 0) AS low_score_realized_count,
  COALESCE(a.high_score_avg_net_pnl_usd, 0) AS high_score_avg_net_pnl_usd,
  COALESCE(a.high_score_median_net_pnl_usd, 0) AS high_score_median_net_pnl_usd,
  COALESCE(a.low_score_avg_net_pnl_usd, 0) AS low_score_avg_net_pnl_usd,
  COALESCE(a.low_score_median_net_pnl_usd, 0) AS low_score_median_net_pnl_usd,
  CASE
    WHEN COALESCE(a.high_score_count, 0) = 0 THEN 'high_score_count=0'
    WHEN COALESCE(a.high_score_realized_count, 0) = 0 THEN 'high_score_realized_count=0'
    WHEN COALESCE(a.low_score_count, 0) = 0 THEN 'low_score_count=0'
    WHEN COALESCE(a.low_score_realized_count, 0) = 0 THEN 'low_score_realized_count=0'
    ELSE ''
  END AS insufficient_reason
FROM horizons h
LEFT JOIN agg a ON a.horizon = h.horizon
ORDER BY h.horizon;

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
      ELSE 'ok'
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
WHERE invalid_reason <> 'ok'
GROUP BY horizon, invalid_reason
ORDER BY horizon, invalid_reason;

-- score_distribution.csv
WITH horizons AS (
  SELECT '1h'::TEXT AS horizon
  UNION ALL SELECT '6h'::TEXT
  UNION ALL SELECT '24h'::TEXT
),
agg AS (
  SELECT
    horizon,
    COUNT(*) AS score_count,
    ROUND(MIN(score_total)::NUMERIC, 6) AS score_min,
    ROUND((percentile_cont(0.10) WITHIN GROUP (ORDER BY score_total))::NUMERIC, 6) AS score_p10,
    ROUND((percentile_cont(0.25) WITHIN GROUP (ORDER BY score_total))::NUMERIC, 6) AS score_p25,
    ROUND((percentile_cont(0.50) WITHIN GROUP (ORDER BY score_total))::NUMERIC, 6) AS score_p50,
    ROUND((percentile_cont(0.75) WITHIN GROUP (ORDER BY score_total))::NUMERIC, 6) AS score_p75,
    ROUND((percentile_cont(0.90) WITHIN GROUP (ORDER BY score_total))::NUMERIC, 6) AS score_p90,
    ROUND(MAX(score_total)::NUMERIC, 6) AS score_max
  FROM shadow_outcome_labels
  GROUP BY horizon
)
SELECT
  h.horizon,
  COALESCE(a.score_count, 0) AS score_count,
  COALESCE(a.score_min, 0) AS score_min,
  COALESCE(a.score_p10, 0) AS score_p10,
  COALESCE(a.score_p25, 0) AS score_p25,
  COALESCE(a.score_p50, 0) AS score_p50,
  COALESCE(a.score_p75, 0) AS score_p75,
  COALESCE(a.score_p90, 0) AS score_p90,
  COALESCE(a.score_max, 0) AS score_max,
  CASE
    WHEN COALESCE(a.score_max, 0) < 80 THEN '80+ bucket empty in current horizon'
    ELSE '80+ bucket active'
  END AS bucket_80plus_assessment
FROM horizons h
LEFT JOIN agg a ON a.horizon = h.horizon
ORDER BY h.horizon;

-- score_edge_diagnostics.csv
WITH realized AS (
  SELECT
    horizon,
    score_total,
    label,
    CAST(simulated_net_pnl_usd AS NUMERIC) AS net_pnl_usd
  FROM shadow_outcome_labels
  WHERE label IN ('win', 'loss')
),
ranked AS (
  SELECT
    horizon,
    score_total,
    label,
    CAST(simulated_net_pnl_usd AS NUMERIC) AS net_pnl_usd,
    NTILE(5) OVER (PARTITION BY horizon ORDER BY score_total ASC, decision_trace_id) AS score_ntile
  FROM shadow_outcome_labels
  WHERE label IN ('win', 'loss')
),
pair_70_60 AS (
  SELECT
    horizon,
    '70-79_vs_60-69'::TEXT AS comparison,
    '70-79'::TEXT AS cohort_a,
    '60-69'::TEXT AS cohort_b,
    COUNT(*) FILTER (WHERE score_total >= 70 AND score_total < 80) AS a_count,
    COUNT(*) FILTER (WHERE score_total >= 60 AND score_total < 70) AS b_count,
    COUNT(*) FILTER (WHERE score_total >= 70 AND score_total < 80) AS a_realized_count,
    COUNT(*) FILTER (WHERE score_total >= 60 AND score_total < 70) AS b_realized_count,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_total >= 70 AND score_total < 80))::NUMERIC, 6) AS a_avg,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_total >= 60 AND score_total < 70))::NUMERIC, 6) AS b_avg,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_total >= 70 AND score_total < 80))::NUMERIC, 6) AS a_median,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_total >= 60 AND score_total < 70))::NUMERIC, 6) AS b_median,
    ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_total >= 70 AND score_total < 80))::NUMERIC, 6) AS a_p10,
    ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_total >= 60 AND score_total < 70))::NUMERIC, 6) AS b_p10,
    ROUND((AVG(CASE WHEN label = 'win' THEN 1.0 ELSE 0.0 END) FILTER (WHERE score_total >= 70 AND score_total < 80))::NUMERIC, 6) AS a_win_rate,
    ROUND((AVG(CASE WHEN label = 'win' THEN 1.0 ELSE 0.0 END) FILTER (WHERE score_total >= 60 AND score_total < 70))::NUMERIC, 6) AS b_win_rate
  FROM realized
  GROUP BY horizon
),
pair_top_bottom AS (
  SELECT
    horizon,
    'top20_vs_bottom20'::TEXT AS comparison,
    'top20%'::TEXT AS cohort_a,
    'bottom20%'::TEXT AS cohort_b,
    COUNT(*) FILTER (WHERE score_ntile = 5) AS a_count,
    COUNT(*) FILTER (WHERE score_ntile = 1) AS b_count,
    COUNT(*) FILTER (WHERE score_ntile = 5) AS a_realized_count,
    COUNT(*) FILTER (WHERE score_ntile = 1) AS b_realized_count,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS a_avg,
    ROUND((AVG(net_pnl_usd) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS b_avg,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS a_median,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS b_median,
    ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS a_p10,
    ROUND((percentile_cont(0.1) WITHIN GROUP (ORDER BY net_pnl_usd) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS b_p10,
    ROUND((AVG(CASE WHEN label = 'win' THEN 1.0 ELSE 0.0 END) FILTER (WHERE score_ntile = 5))::NUMERIC, 6) AS a_win_rate,
    ROUND((AVG(CASE WHEN label = 'win' THEN 1.0 ELSE 0.0 END) FILTER (WHERE score_ntile = 1))::NUMERIC, 6) AS b_win_rate
  FROM ranked
  GROUP BY horizon
),
combined AS (
  SELECT * FROM pair_70_60
  UNION ALL
  SELECT * FROM pair_top_bottom
)
SELECT
  horizon,
  comparison,
  cohort_a,
  cohort_b,
  COALESCE(a_count, 0) AS cohort_a_count,
  COALESCE(b_count, 0) AS cohort_b_count,
  COALESCE(a_realized_count, 0) AS cohort_a_realized_count,
  COALESCE(b_realized_count, 0) AS cohort_b_realized_count,
  COALESCE(a_avg, 0) AS cohort_a_avg_net_pnl_usd,
  COALESCE(a_median, 0) AS cohort_a_median_net_pnl_usd,
  COALESCE(a_p10, 0) AS cohort_a_p10_net_pnl_usd,
  COALESCE(a_win_rate, 0) AS cohort_a_win_rate,
  COALESCE(b_avg, 0) AS cohort_b_avg_net_pnl_usd,
  COALESCE(b_median, 0) AS cohort_b_median_net_pnl_usd,
  COALESCE(b_p10, 0) AS cohort_b_p10_net_pnl_usd,
  COALESCE(b_win_rate, 0) AS cohort_b_win_rate,
  CASE
    WHEN COALESCE(a_realized_count, 0) = 0 THEN 'insufficient'
    WHEN COALESCE(b_realized_count, 0) = 0 THEN 'insufficient'
    WHEN COALESCE(a_avg, 0) > COALESCE(b_avg, 0)
      AND COALESCE(a_median, 0) >= COALESCE(b_median, 0)
      AND COALESCE(a_p10, 0) >= COALESCE(b_p10, 0)
      AND COALESCE(a_win_rate, 0) >= COALESCE(b_win_rate, 0) THEN 'better'
    WHEN COALESCE(a_avg, 0) < COALESCE(b_avg, 0)
      AND COALESCE(a_median, 0) <= COALESCE(b_median, 0)
      AND COALESCE(a_p10, 0) <= COALESCE(b_p10, 0)
      AND COALESCE(a_win_rate, 0) <= COALESCE(b_win_rate, 0) THEN 'worse'
    ELSE 'flat'
  END AS score_rank_signal,
  CASE
    WHEN COALESCE(a_realized_count, 0) = 0 THEN cohort_a || '_realized_count=0'
    WHEN COALESCE(b_realized_count, 0) = 0 THEN cohort_b || '_realized_count=0'
    ELSE ''
  END AS insufficient_reason
FROM combined
ORDER BY horizon, comparison;

-- outlier_concentration.csv
WITH realized AS (
  SELECT
    horizon,
    CAST(simulated_net_pnl_usd AS NUMERIC) AS net_pnl_usd,
    ROW_NUMBER() OVER (PARTITION BY horizon ORDER BY CAST(simulated_net_pnl_usd AS NUMERIC) DESC, decision_trace_id) AS rn_desc,
    ROW_NUMBER() OVER (PARTITION BY horizon ORDER BY CAST(simulated_net_pnl_usd AS NUMERIC) ASC, decision_trace_id) AS rn_asc,
    COUNT(*) OVER (PARTITION BY horizon) AS total_count
  FROM shadow_outcome_labels
  WHERE label IN ('win', 'loss')
),
agg AS (
  SELECT
    horizon,
    MAX(total_count) AS realized_count,
    ROUND(AVG(net_pnl_usd)::NUMERIC, 6) AS avg_net_pnl_usd,
    ROUND(SUM(net_pnl_usd)::NUMERIC, 6) AS total_net_pnl_usd,
    ROUND(
      COALESCE(SUM(net_pnl_usd) FILTER (WHERE rn_desc <= GREATEST(1, CEIL(total_count * 0.01))), 0)::NUMERIC,
      6
    ) AS top_1pct_net_pnl_usd,
    ROUND(
      COALESCE(
        SUM(net_pnl_usd) FILTER (WHERE rn_desc <= GREATEST(1, CEIL(total_count * 0.01))) /
        NULLIF(SUM(net_pnl_usd), 0),
        0
      )::NUMERIC,
      6
    ) AS top_1pct_pnl_share,
    ROUND(
      AVG(net_pnl_usd) FILTER (
        WHERE rn_asc > GREATEST(1, CEIL(total_count * 0.05))
          AND rn_desc > GREATEST(1, CEIL(total_count * 0.05))
      )::NUMERIC,
      6
    ) AS trimmed_mean_5pct
  FROM realized
  GROUP BY horizon
)
SELECT
  horizon,
  COALESCE(realized_count, 0) AS realized_count,
  COALESCE(avg_net_pnl_usd, 0) AS avg_net_pnl_usd,
  COALESCE(trimmed_mean_5pct, 0) AS trimmed_mean_5pct,
  COALESCE(top_1pct_net_pnl_usd, 0) AS top_1pct_net_pnl_usd,
  COALESCE(top_1pct_pnl_share, 0) AS top_1pct_pnl_share,
  CASE
    WHEN COALESCE(realized_count, 0) = 0 THEN 'insufficient'
    WHEN COALESCE(top_1pct_pnl_share, 0) >= 0.50 THEN 'WARN'
    WHEN ABS(COALESCE(avg_net_pnl_usd, 0) - COALESCE(trimmed_mean_5pct, 0)) > ABS(COALESCE(avg_net_pnl_usd, 0)) * 0.5 THEN 'WARN'
    ELSE 'OK'
  END AS outlier_warning
FROM agg
ORDER BY horizon;

-- stale_mark_summary.csv
SELECT
  COALESCE(MIN(mark_time), 0) AS min_mark_time,
  COALESCE(MAX(mark_time), 0) AS max_mark_time,
  COALESCE(COUNT(*), 0) AS mark_count,
  COALESCE(COUNT(DISTINCT pool_id), 0) AS distinct_pool_count,
  COALESCE(COUNT(DISTINCT position_id), 0) AS distinct_position_count
FROM shadow_position_marks;

-- stale_mark_pools.csv
SELECT
  pool_id,
  COUNT(*) AS mark_count,
  COALESCE(MIN(mark_time), 0) AS min_mark_time,
  COALESCE(MAX(mark_time), 0) AS max_mark_time
FROM shadow_position_marks
GROUP BY pool_id
ORDER BY mark_count ASC, max_mark_time ASC, pool_id ASC
LIMIT 30;

-- materialized_time_distribution.csv
WITH ranked AS (
  SELECT
    horizon,
    to_char(date_trunc('hour', to_timestamp(decision_time)), 'YYYY-MM-DD HH24:00') AS hour_bucket,
    COUNT(*) AS samples,
    ROW_NUMBER() OVER (
      PARTITION BY horizon
      ORDER BY COUNT(*) DESC, date_trunc('hour', to_timestamp(decision_time)) DESC
    ) AS bucket_rank
  FROM shadow_outcome_labels
  WHERE horizon IN ('6h', '24h')
  GROUP BY horizon, date_trunc('hour', to_timestamp(decision_time))
)
SELECT horizon, hour_bucket, samples
FROM ranked
WHERE bucket_rank <= 12
ORDER BY horizon, samples DESC, hour_bucket DESC;

-- materialized_pool_distribution.csv
WITH ranked AS (
  SELECT
    horizon,
    pool_id,
    COUNT(*) AS samples,
    ROW_NUMBER() OVER (
      PARTITION BY horizon
      ORDER BY COUNT(*) DESC, pool_id ASC
    ) AS pool_rank
  FROM shadow_outcome_labels
  WHERE horizon IN ('6h', '24h')
  GROUP BY horizon, pool_id
)
SELECT horizon, pool_id, samples
FROM ranked
WHERE pool_rank <= 12
ORDER BY horizon, samples DESC, pool_id ASC;
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

read_label_count_for_horizon() {
  local horizon="$1"
  psql "$POSTGRES_DSN" -X -A -t -c "SELECT COUNT(*) FROM shadow_outcome_labels WHERE horizon = '${horizon}';" | tr -d '[:space:]'
}

format_pct() {
  local numerator="${1:-0}"
  local denominator="${2:-0}"
  awk -v n="$numerator" -v d="$denominator" 'BEGIN { if (d <= 0) printf "0.00%%"; else printf "%.2f%%", (n*100.0)/d; }'
}

format_rate_per_min() {
  local delta="${1:-0}"
  local seconds="${2:-0}"
  awk -v d="$delta" -v s="$seconds" 'BEGIN { if (s <= 0) printf "0.00"; else printf "%.2f", d / (s/60.0); }'
}

estimate_target_time() {
  local total="${1:-0}"
  local current="${2:-0}"
  local delta="${3:-0}"
  local seconds="${4:-0}"
  local target_pct="${5:-0}"
  awk -v total="$total" -v current="$current" -v delta="$delta" -v seconds="$seconds" -v target_pct="$target_pct" '
    BEGIN {
      if (delta <= 0 || seconds <= 0) {
        printf "unknown";
      } else if (total <= 0) {
        printf "unknown";
      } else {
        target_count = (target_pct / 100.0) * total;
        missing = target_count - current;
        if (missing <= 0) {
          printf "reached";
        } else {
          mins = missing / (delta / (seconds / 60.0));
          printf "%.0f min (~%.1f h)", mins, mins/60.0;
        }
      }
    }
  '
}

estimate_catchup_time() {
  local missing="${1:-0}"
  local delta="${2:-0}"
  local seconds="${3:-0}"
  awk -v missing="$missing" -v delta="$delta" -v seconds="$seconds" '
    BEGIN {
      if (delta <= 0 || seconds <= 0) {
        printf "unknown";
      } else {
        mins = missing / (delta / (seconds / 60.0));
        printf "%.0f min (~%.1f h)", mins, mins/60.0;
      }
    }
  '
}

read_timeout_for_horizon() {
  local horizon="$1"
  local key=""
  case "$horizon" in
    1h) key="LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS_1H" ;;
    6h) key="LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS_6H" ;;
    24h) key="LPBOT_SHADOW_OBS_BACKFILL_TIMEOUT_SECONDS_24H" ;;
  esac
  if [[ -n "$key" ]]; then
    local value="${!key:-}"
    if [[ -n "$value" ]]; then
      printf '%s\n' "$value"
      return 0
    fi
  fi
  printf '%s\n' "$BACKFILL_TIMEOUT_SECONDS"
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
- [BACKFILL_MATERIALIZATION_DIAG_CN.md](${SNAPSHOT_DIR}/BACKFILL_MATERIALIZATION_DIAG_CN.md)
- [BACKLOG_CATCHUP_SUMMARY_CN.md](${SNAPSHOT_DIR}/BACKLOG_CATCHUP_SUMMARY_CN.md)
- [outcome_counts.csv](${SNAPSHOT_DIR}/outcome_counts.csv)
- [bucket_stats.csv](${SNAPSHOT_DIR}/bucket_stats.csv)
- [high_low_score_diagnostics.csv](${SNAPSHOT_DIR}/high_low_score_diagnostics.csv)
- [invalid_reason_counts.csv](${SNAPSHOT_DIR}/invalid_reason_counts.csv)
- [score_distribution.csv](${SNAPSHOT_DIR}/score_distribution.csv)
- [score_edge_diagnostics.csv](${SNAPSHOT_DIR}/score_edge_diagnostics.csv)
- [outlier_concentration.csv](${SNAPSHOT_DIR}/outlier_concentration.csv)
- [stale_mark_summary.csv](${SNAPSHOT_DIR}/stale_mark_summary.csv)
- [stale_mark_pools.csv](${SNAPSHOT_DIR}/stale_mark_pools.csv)
- [materialized_time_distribution.csv](${SNAPSHOT_DIR}/materialized_time_distribution.csv)
- [materialized_pool_distribution.csv](${SNAPSHOT_DIR}/materialized_pool_distribution.csv)
- [RAW_SQL_QUERIES.sql](${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql)
EOF
}

run_backfill_for_horizon() {
  local horizon="$1"
  local stderr_log="${SNAPSHOT_DIR}/backfill_${horizon}.stderr.log"
  local timeout_seconds
  timeout_seconds="$(read_timeout_for_horizon "$horizon")"
  if ! command -v timeout >/dev/null 2>&1; then
    echo "SKIPPED(no-timeout)"
    return 0
  fi
  set +e
  timeout --signal=TERM "${timeout_seconds}" \
    go run -tags shadow ./cmd/lpbot \
      --config="${CONFIG_PATH}" \
      --shadow-outcomes-backfill \
      --shadow-outcomes-backfill-horizon="${horizon}" \
      >/dev/null 2>"${stderr_log}"
  local rc=$?
  set -e
  if [[ "$rc" == "0" ]]; then
    echo "OK"
    return 0
  fi
  if [[ "$rc" == "124" || "$rc" == "143" ]]; then
    echo "TIMEBOXED"
  else
    echo "ERROR(${rc})"
  fi
}

generate_backfill_materialization_diag() {
  local mature_row labels_by_horizon missing_6h missing_24h
  mature_row="$(psql "$POSTGRES_DSN" -X -A -t -F '|' -c "
    SELECT
      COUNT(*) FILTER (WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 3600) AS mature_1h,
      COUNT(*) FILTER (WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 21600) AS mature_6h,
      COUNT(*) FILTER (WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 86400) AS mature_24h,
      MIN(tick_time),
      MAX(tick_time),
      COUNT(*)
    FROM shadow_decision_trace;
  ")"
  IFS='|' read -r mature_1h mature_6h mature_24h min_tick_time max_tick_time total_traces <<<"${mature_row}"

  labels_by_horizon="$(psql "$POSTGRES_DSN" -X -A -t -F '|' -c "
    SELECT horizon, label, COUNT(*)
    FROM shadow_outcome_labels
    GROUP BY horizon, label
    ORDER BY horizon, label;
  ")"

  local label_count_rows
  label_count_rows="$(psql "$POSTGRES_DSN" -X -A -t -F '|' -c "
    SELECT horizon, COUNT(*)
    FROM shadow_outcome_labels
    GROUP BY horizon
    ORDER BY horizon;
  ")"
  local labels_1h=0 labels_6h=0 labels_24h=0
  while IFS='|' read -r horizon count; do
    [[ -z "${horizon:-}" ]] && continue
    case "$horizon" in
      1h) labels_1h="$count" ;;
      6h) labels_6h="$count" ;;
      24h) labels_24h="$count" ;;
    esac
  done <<<"${label_count_rows}"
  AFTER_LABELS_6H="${labels_6h:-0}"
  AFTER_LABELS_24H="${labels_24h:-0}"

  missing_6h="$(psql "$POSTGRES_DSN" -X -A -t -c "
    SELECT COUNT(*)
    FROM shadow_decision_trace d
    WHERE d.tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 21600
      AND NOT EXISTS (
        SELECT 1 FROM shadow_outcome_labels o
        WHERE o.decision_trace_id = d.trace_id
          AND o.horizon = '6h'
      );
  " | tr -d '[:space:]')"
  missing_24h="$(psql "$POSTGRES_DSN" -X -A -t -c "
    SELECT COUNT(*)
    FROM shadow_decision_trace d
    WHERE d.tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 86400
      AND NOT EXISTS (
        SELECT 1 FROM shadow_outcome_labels o
        WHERE o.decision_trace_id = d.trace_id
          AND o.horizon = '24h'
      );
  " | tr -d '[:space:]')"

  local need_horizon_filter="yes"
  local bottleneck="unknown"
  local conclusion="这是数据链路问题，需要优先修复 materialization/backfill。"
  local prior_single_timebox_1h_only="no"
  if [[ "${mature_6h:-0}" == "0" && "${mature_24h:-0}" == "0" ]]; then
    need_horizon_filter="no"
    bottleneck="no mature 6h/24h decisions yet"
    conclusion="当前不是策略问题，也不是 materialization bug；6h/24h 样本尚未成熟。"
  elif [[ "${labels_6h:-0}" == "0" || "${labels_24h:-0}" == "0" ]]; then
    bottleneck="mature decisions exist but 6h/24h labels are missing"
    prior_single_timebox_1h_only="yes"
  elif [[ "${missing_6h:-0}" != "0" || "${missing_24h:-0}" != "0" ]]; then
    bottleneck="6h/24h started materializing but backlog remains after per-horizon backfill"
    conclusion="这不是策略问题；这是 backfill 吞吐/时间预算问题。旧的单次 60s backfill 会让 1h 优先吃掉预算，新的 horizon-filter 已经证明 6h/24h 可以落表，但当前 timebox 仍不足以清空 backlog。"
    prior_single_timebox_1h_only="yes"
  fi

  cat >"${SNAPSHOT_DIR}/BACKFILL_MATERIALIZATION_DIAG_CN.md" <<EOF
# Backfill Materialization Diagnostic

- 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- snapshot 目录: \`${SNAPSHOT_DIR}\`

## Matured Decision Counts

- mature_1h: ${mature_1h:-0}
- mature_6h: ${mature_6h:-0}
- mature_24h: ${mature_24h:-0}
- min_tick_time: ${min_tick_time:-0}
- max_tick_time: ${max_tick_time:-0}
- shadow_decision_trace total: ${total_traces:-0}

## Materialized Label Counts

- labels_1h: ${labels_1h:-0}
- labels_6h: ${labels_6h:-0}
- labels_24h: ${labels_24h:-0}
- missing_6h: ${missing_6h:-0}
- missing_24h: ${missing_24h:-0}

## Horizon Label Breakdown

\`\`\`
${labels_by_horizon}
\`\`\`

## Backfill Execution

- backfill_1h_status: ${BACKFILL_1H_STATUS}
- backfill_6h_status: ${BACKFILL_6H_STATUS}
- backfill_24h_status: ${BACKFILL_24H_STATUS}
- previous single-60s backfill likely only completed 1h: ${prior_single_timebox_1h_only}
- horizon-filter needed: ${need_horizon_filter}

## Diagnosis

- bottleneck: ${bottleneck}
- conclusion: ${conclusion}
EOF
}

generate_backlog_catchup_summary() {
  local mature_row
  mature_row="$(psql "$POSTGRES_DSN" -X -A -t -F '|' -c "
    SELECT
      COUNT(*) FILTER (WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 21600) AS mature_6h,
      COUNT(*) FILTER (WHERE tick_time <= EXTRACT(EPOCH FROM NOW())::BIGINT - 86400) AS mature_24h
    FROM shadow_decision_trace;
  ")"
  local mature_6h mature_24h
  IFS='|' read -r mature_6h mature_24h <<<"${mature_row}"

  local labels_6h labels_24h missing_6h missing_24h delta_6h delta_24h
  labels_6h="${AFTER_LABELS_6H:-0}"
  labels_24h="${AFTER_LABELS_24H:-0}"
  missing_6h=$(( ${mature_6h:-0} - ${labels_6h:-0} ))
  missing_24h=$(( ${mature_24h:-0} - ${labels_24h:-0} ))
  if (( missing_6h < 0 )); then missing_6h=0; fi
  if (( missing_24h < 0 )); then missing_24h=0; fi
  delta_6h=$(( ${labels_6h:-0} - ${BEFORE_LABELS_6H:-0} ))
  delta_24h=$(( ${labels_24h:-0} - ${BEFORE_LABELS_24H:-0} ))

  local coverage_6h coverage_24h coverage_before_6h coverage_before_24h coverage_delta_6h coverage_delta_24h
  local elapsed_seconds labels_per_min_6h labels_per_min_24h catchup_eta_6h catchup_eta_24h
  local eta_30_6h eta_30_24h eta_70_6h eta_70_24h
  coverage_6h="$(format_pct "${labels_6h:-0}" "${mature_6h:-0}")"
  coverage_24h="$(format_pct "${labels_24h:-0}" "${mature_24h:-0}")"
  coverage_before_6h="$(format_pct "${BEFORE_LABELS_6H:-0}" "${mature_6h:-0}")"
  coverage_before_24h="$(format_pct "${BEFORE_LABELS_24H:-0}" "${mature_24h:-0}")"
  elapsed_seconds=$(( RUN_ENDED_EPOCH - RUN_STARTED_EPOCH ))
  labels_per_min_6h="$(format_rate_per_min "${delta_6h:-0}" "${elapsed_seconds:-0}")"
  labels_per_min_24h="$(format_rate_per_min "${delta_24h:-0}" "${elapsed_seconds:-0}")"
  catchup_eta_6h="$(estimate_catchup_time "${missing_6h:-0}" "${delta_6h:-0}" "${elapsed_seconds:-0}")"
  catchup_eta_24h="$(estimate_catchup_time "${missing_24h:-0}" "${delta_24h:-0}" "${elapsed_seconds:-0}")"
  coverage_delta_6h="$(awk -v before="${BEFORE_LABELS_6H:-0}" -v after="${labels_6h:-0}" -v total="${mature_6h:-0}" 'BEGIN { if (total <= 0) printf "0.00pp"; else printf "%.2fpp", ((after-before)*100.0)/total; }')"
  coverage_delta_24h="$(awk -v before="${BEFORE_LABELS_24H:-0}" -v after="${labels_24h:-0}" -v total="${mature_24h:-0}" 'BEGIN { if (total <= 0) printf "0.00pp"; else printf "%.2fpp", ((after-before)*100.0)/total; }')"
  eta_30_6h="$(estimate_target_time "${mature_6h:-0}" "${labels_6h:-0}" "${delta_6h:-0}" "${elapsed_seconds:-0}" "30")"
  eta_30_24h="$(estimate_target_time "${mature_24h:-0}" "${labels_24h:-0}" "${delta_24h:-0}" "${elapsed_seconds:-0}" "30")"
  eta_70_6h="$(estimate_target_time "${mature_6h:-0}" "${labels_6h:-0}" "${delta_6h:-0}" "${elapsed_seconds:-0}" "70")"
  eta_70_24h="$(estimate_target_time "${mature_24h:-0}" "${labels_24h:-0}" "${delta_24h:-0}" "${elapsed_seconds:-0}" "70")"

  local edge_csv="${SNAPSHOT_DIR}/score_edge_diagnostics.csv"
  local invalid_csv="${SNAPSHOT_DIR}/invalid_reason_counts.csv"
  local time_csv="${SNAPSHOT_DIR}/materialized_time_distribution.csv"
  local pool_csv="${SNAPSHOT_DIR}/materialized_pool_distribution.csv"
  local six_quantile twentyfour_quantile six_adjacent twentyfour_adjacent
  six_quantile="$(awk -F, '$1=="6h" && $2=="top20_vs_bottom20" {printf "avg=%s median=%s p10=%s win_rate=%s signal=%s", $9, $10, $11, $12, $17}' "$edge_csv")"
  twentyfour_quantile="$(awk -F, '$1=="24h" && $2=="top20_vs_bottom20" {printf "avg=%s median=%s p10=%s win_rate=%s signal=%s", $9, $10, $11, $12, $17}' "$edge_csv")"
  six_adjacent="$(awk -F, '$1=="6h" && $2=="70-79_vs_60-69" {printf "avg=%s median=%s p10=%s win_rate=%s signal=%s", $9, $10, $11, $12, $17}' "$edge_csv")"
  twentyfour_adjacent="$(awk -F, '$1=="24h" && $2=="70-79_vs_60-69" {printf "avg=%s median=%s p10=%s win_rate=%s signal=%s", $9, $10, $11, $12, $17}' "$edge_csv")"

  local invalid_6h invalid_24h stale_6h stale_24h stale_share_6h stale_share_24h
  invalid_6h="$(awk -F'[ :%]+' '/## 6h/{seen=1} seen && /- invalid_rate:/{print $3; exit}' "${SNAPSHOT_DIR}/REPORT_SHADOW_OUTCOMES_CN.md")"
  invalid_24h="$(awk -F'[ :%]+' '/## 24h/{seen=1} seen && /- invalid_rate:/{print $3; exit}' "${SNAPSHOT_DIR}/REPORT_SHADOW_OUTCOMES_CN.md")"
  stale_6h="$(awk -F, '$1=="6h" && $2=="stale mark" {print $3}' "$invalid_csv")"
  stale_24h="$(awk -F, '$1=="24h" && $2=="stale mark" {print $3}' "$invalid_csv")"
  stale_share_6h="$(format_pct "${stale_6h:-0}" "${mature_6h:-0}")"
  stale_share_24h="$(format_pct "${stale_24h:-0}" "${mature_24h:-0}")"

  local top_pool_share_6h top_pool_share_24h top_hour_share_6h top_hour_share_24h sample_bias_warn="OK"
  top_pool_share_6h="$(awk -F, -v labels="${labels_6h:-0}" '$1=="6h" { if (labels > 0) { printf "%.2f%%", ($3*100.0)/labels; exit } }' "$pool_csv")"
  top_pool_share_24h="$(awk -F, -v labels="${labels_24h:-0}" '$1=="24h" { if (labels > 0) { printf "%.2f%%", ($3*100.0)/labels; exit } }' "$pool_csv")"
  top_hour_share_6h="$(awk -F, -v labels="${labels_6h:-0}" '$1=="6h" { if (labels > 0) { printf "%.2f%%", ($3*100.0)/labels; exit } }' "$time_csv")"
  top_hour_share_24h="$(awk -F, -v labels="${labels_24h:-0}" '$1=="24h" { if (labels > 0) { printf "%.2f%%", ($3*100.0)/labels; exit } }' "$time_csv")"
  if awk -v p6="${top_pool_share_6h%%%}" -v p24="${top_pool_share_24h%%%}" -v h6="${top_hour_share_6h%%%}" -v h24="${top_hour_share_24h%%%}" 'BEGIN { exit !((p6+0)>=50 || (p24+0)>=50 || (h6+0)>=50 || (h24+0)>=50) }'; then
    sample_bias_warn="SAMPLE_BIAS_WARN"
  fi

  local bucket_csv="${SNAPSHOT_DIR}/bucket_stats.csv"
  local top_24h_score_buckets top_24h_pools top_24h_hours
  top_24h_score_buckets="$(awk -F, '$1=="score" && $2=="24h" {printf "- %s: samples=%s win_rate=%s avg=%s median=%s\n", $3, $4, $8, $9, $10}' "$bucket_csv" | head -n 5)"
  top_24h_pools="$(awk -F, -v labels="${labels_24h:-0}" '$1=="24h" { if (labels > 0) { printf "- %s: labels=%s share=%.2f%%\n", $2, $3, ($3*100.0)/labels } else { printf "- %s: labels=%s share=0.00%%\n", $2, $3 } }' "$pool_csv" | head -n 5)"
  top_24h_hours="$(awk -F, -v labels="${labels_24h:-0}" '$1=="24h" { if (labels > 0) { printf "- %s: labels=%s share=%.2f%%\n", $2, $3, ($3*100.0)/labels } else { printf "- %s: labels=%s share=0.00%%\n", $2, $3 } }' "$time_csv" | head -n 5)"
  if [[ -z "${top_24h_score_buckets}" ]]; then top_24h_score_buckets="- unavailable"; fi
  if [[ -z "${top_24h_pools}" ]]; then top_24h_pools="- unavailable"; fi
  if [[ -z "${top_24h_hours}" ]]; then top_24h_hours="- unavailable"; fi

  cat >"${SNAPSHOT_DIR}/BACKLOG_CATCHUP_SUMMARY_CN.md" <<EOF
# Backlog Catch-up Summary

- 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- latest report directory: \`${SNAPSHOT_DIR}\`
- verdict: EARLY_SIGNAL_ONLY

## Coverage

- mature_6h: ${mature_6h:-0}
- labels_6h: ${labels_6h:-0}
- missing_6h: ${missing_6h:-0}
- coverage_6h_before: ${coverage_before_6h}
- coverage_6h: ${coverage_6h}
- coverage_delta_6h: ${coverage_delta_6h}
- mature_24h: ${mature_24h:-0}
- labels_24h: ${labels_24h:-0}
- missing_24h: ${missing_24h:-0}
- coverage_24h_before: ${coverage_before_24h}
- coverage_24h: ${coverage_24h}
- coverage_delta_24h: ${coverage_delta_24h}

## This Run

- delta_labels_6h: ${delta_6h:-0}
- delta_labels_24h: ${delta_24h:-0}
- labels_per_min_6h: ${labels_per_min_6h}
- labels_per_min_24h: ${labels_per_min_24h}
- estimated_catchup_time_6h: ${catchup_eta_6h}
- estimated_catchup_time_24h: ${catchup_eta_24h}
- estimated_time_to_30pct_6h: ${eta_30_6h}
- estimated_time_to_30pct_24h: ${eta_30_24h}
- estimated_time_to_70pct_6h: ${eta_70_6h}
- estimated_time_to_70pct_24h: ${eta_70_24h}

## Early Signal

- 6h top20 vs bottom20: ${six_quantile:-unavailable}
- 24h top20 vs bottom20: ${twentyfour_quantile:-unavailable}
- 6h 70-79 vs 60-69: ${six_adjacent:-unavailable}
- 24h 70-79 vs 60-69: ${twentyfour_adjacent:-unavailable}
- 6h invalid_rate: ${invalid_6h:-0}%
- 24h invalid_rate: ${invalid_24h:-0}%
- 6h stale_mark_share: ${stale_share_6h}
- 24h stale_mark_share: ${stale_share_24h}

## 24h Detail

- verdict: EARLY_SIGNAL_ONLY
- 24h score bucket:
${top_24h_score_buckets}
- 24h pool_id distribution:
${top_24h_pools}
- 24h time bucket distribution:
${top_24h_hours}

## Sample Bias

- top_pool_share_6h: ${top_pool_share_6h:-0.00%}
- top_pool_share_24h: ${top_pool_share_24h:-0.00%}
- top_hour_share_6h: ${top_hour_share_6h:-0.00%}
- top_hour_share_24h: ${top_hour_share_24h:-0.00%}
- sample_bias: ${sample_bias_warn}
EOF
}

load_env
cd "$ROOT_DIR"
mkdir -p "$SNAPSHOT_DIR"
BEFORE_LABELS_6H="$(read_label_count_for_horizon "6h")"
BEFORE_LABELS_24H="$(read_label_count_for_horizon "24h")"
RUN_STARTED_EPOCH="$(date +%s)"

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

exec 9>"${BACKFILL_LOCK_FILE}"
if flock -w "${BACKFILL_LOCK_WAIT_SECONDS}" 9; then
  BACKFILL_24H_STATUS="SKIPPED"
  BACKFILL_6H_STATUS="SKIPPED"
  BACKFILL_1H_STATUS="SKIPPED"
  for horizon in ${BACKFILL_SEQUENCE}; do
    case "$horizon" in
      24h)
        current_status="$(run_backfill_for_horizon "24h")"
        if [[ "${BACKFILL_24H_STATUS}" == "SKIPPED" ]]; then
          BACKFILL_24H_STATUS="${current_status}"
        else
          BACKFILL_24H_STATUS="${BACKFILL_24H_STATUS}+${current_status}"
        fi
        ;;
      6h)
        current_status="$(run_backfill_for_horizon "6h")"
        if [[ "${BACKFILL_6H_STATUS}" == "SKIPPED" ]]; then
          BACKFILL_6H_STATUS="${current_status}"
        else
          BACKFILL_6H_STATUS="${BACKFILL_6H_STATUS}+${current_status}"
        fi
        ;;
      1h)
        current_status="$(run_backfill_for_horizon "1h")"
        if [[ "${BACKFILL_1H_STATUS}" == "SKIPPED" ]]; then
          BACKFILL_1H_STATUS="${current_status}"
        else
          BACKFILL_1H_STATUS="${BACKFILL_1H_STATUS}+${current_status}"
        fi
        ;;
    esac
  done
  flock -u 9
else
  BACKFILL_24H_STATUS="LOCKED"
  BACKFILL_6H_STATUS="LOCKED"
  BACKFILL_1H_STATUS="LOCKED"
fi
backfill_status="1h=${BACKFILL_1H_STATUS},6h=${BACKFILL_6H_STATUS},24h=${BACKFILL_24H_STATUS}"
RUN_ENDED_EPOCH="$(date +%s)"

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
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- score_distribution.csv" "${SNAPSHOT_DIR}/score_distribution.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- score_edge_diagnostics.csv" "${SNAPSHOT_DIR}/score_edge_diagnostics.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- outlier_concentration.csv" "${SNAPSHOT_DIR}/outlier_concentration.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- stale_mark_summary.csv" "${SNAPSHOT_DIR}/stale_mark_summary.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- stale_mark_pools.csv" "${SNAPSHOT_DIR}/stale_mark_pools.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- materialized_time_distribution.csv" "${SNAPSHOT_DIR}/materialized_time_distribution.csv"
run_query_to_csv "${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql" "-- materialized_pool_distribution.csv" "${SNAPSHOT_DIR}/materialized_pool_distribution.csv"
generate_trend_summary
generate_backfill_materialization_diag
generate_backlog_catchup_summary
write_summary "$readiness_status" "$backfill_status" "$report_status"

printf '[shadow-observation] dir=%s readiness=%s backfill=%s report=%s\n' \
  "$SNAPSHOT_DIR" "$readiness_status" "$backfill_status" "$report_status"
