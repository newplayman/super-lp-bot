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
- [BACKFILL_MATERIALIZATION_DIAG_CN.md](${SNAPSHOT_DIR}/BACKFILL_MATERIALIZATION_DIAG_CN.md)
- [outcome_counts.csv](${SNAPSHOT_DIR}/outcome_counts.csv)
- [bucket_stats.csv](${SNAPSHOT_DIR}/bucket_stats.csv)
- [high_low_score_diagnostics.csv](${SNAPSHOT_DIR}/high_low_score_diagnostics.csv)
- [invalid_reason_counts.csv](${SNAPSHOT_DIR}/invalid_reason_counts.csv)
- [score_distribution.csv](${SNAPSHOT_DIR}/score_distribution.csv)
- [score_edge_diagnostics.csv](${SNAPSHOT_DIR}/score_edge_diagnostics.csv)
- [outlier_concentration.csv](${SNAPSHOT_DIR}/outlier_concentration.csv)
- [stale_mark_summary.csv](${SNAPSHOT_DIR}/stale_mark_summary.csv)
- [stale_mark_pools.csv](${SNAPSHOT_DIR}/stale_mark_pools.csv)
- [RAW_SQL_QUERIES.sql](${SNAPSHOT_DIR}/RAW_SQL_QUERIES.sql)
EOF
}

run_backfill_for_horizon() {
  local horizon="$1"
  local stderr_log="${SNAPSHOT_DIR}/backfill_${horizon}.stderr.log"
  if ! command -v timeout >/dev/null 2>&1; then
    echo "SKIPPED(no-timeout)"
    return 0
  fi
  if timeout --signal=TERM "${BACKFILL_TIMEOUT_SECONDS}" \
    go run -tags shadow ./cmd/lpbot \
      --config="${CONFIG_PATH}" \
      --shadow-outcomes-backfill \
      --shadow-outcomes-backfill-horizon="${horizon}" \
      >/dev/null 2>"${stderr_log}"; then
    echo "OK"
    return 0
  fi
  local rc=$?
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
  if [[ "${mature_6h:-0}" == "0" && "${mature_24h:-0}" == "0" ]]; then
    need_horizon_filter="no"
    bottleneck="no mature 6h/24h decisions yet"
    conclusion="当前不是策略问题，也不是 materialization bug；6h/24h 样本尚未成熟。"
  elif [[ "${labels_6h:-0}" == "0" || "${labels_24h:-0}" == "0" ]]; then
    bottleneck="mature decisions exist but 6h/24h labels are missing"
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
- previous single-60s backfill likely only completed 1h: $( [[ "${mature_6h:-0}" != "0" && "${labels_6h:-0}" == "0" ]] && echo "yes" || echo "no" )
- horizon-filter needed: ${need_horizon_filter}

## Diagnosis

- bottleneck: ${bottleneck}
- conclusion: ${conclusion}
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

BACKFILL_1H_STATUS="$(run_backfill_for_horizon "1h")"
BACKFILL_6H_STATUS="$(run_backfill_for_horizon "6h")"
BACKFILL_24H_STATUS="$(run_backfill_for_horizon "24h")"
backfill_status="1h=${BACKFILL_1H_STATUS},6h=${BACKFILL_6H_STATUS},24h=${BACKFILL_24H_STATUS}"

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
generate_trend_summary
generate_backfill_materialization_diag
write_summary "$readiness_status" "$backfill_status" "$report_status"

printf '[shadow-observation] dir=%s readiness=%s backfill=%s report=%s\n' \
  "$SNAPSHOT_DIR" "$readiness_status" "$backfill_status" "$report_status"
