#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${LPBOT_LIVE_READINESS_CONFIG:-configs/config.live.toml}"
REPORT_PATH="${LPBOT_LIVE_READINESS_REPORT_PATH:-READINESS_REPORT_CN.md}"
EXPECTED_COMMIT="${LPBOT_LIVE_EXPECT_COMMIT:-}"

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then set -a; . ./.env.postgres; set +a; fi
  if [[ -f ./.env.live ]]; then set -a; . ./.env.live; set +a; fi
  if [[ -f ./.env.canary ]]; then set -a; . ./.env.canary; set +a; fi
  export POSTGRES_DSN="${POSTGRES_DSN:-${DATABASE_URL:-}}"
}

have_psql() {
  command -v psql >/dev/null 2>&1
}

check_env_var() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    echo "OK"
  else
    echo "MISSING"
  fi
}

query_bool() {
  local sql="$1"
  psql "$POSTGRES_DSN" -X -A -t -c "$sql" 2>/dev/null | tr -d '[:space:]'
}

query_value() {
  local sql="$1"
  psql "$POSTGRES_DSN" -X -A -F $'\t' -P pager=off -t -c "$sql" 2>/dev/null | tr -d '\r'
}

load_env
cd "$ROOT_DIR"

CURRENT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
COMMIT_STATUS="OK"
if [[ -n "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
  COMMIT_STATUS="MISMATCH"
fi

CONFIG_STATUS="OK"
if [[ ! -f "$CONFIG_PATH" ]]; then
  CONFIG_STATUS="MISSING"
fi

declare -a REQUIRED_VARS=(
  "POSTGRES_DSN"
  "BASE_RPC_PRIMARY"
  "LIVE_WALLET_ADDRESS"
  "NPM_BASE_ADDRESS"
  "FLASHBOTS_RPC_URL"
  "WALLET_PASSPHRASE"
)

declare -A ENV_STATUS
for name in "${REQUIRED_VARS[@]}"; do
  ENV_STATUS["$name"]="$(check_env_var "$name")"
done

SCHEMA_STATUS="SKIPPED"
SNAPSHOT_STATUS="SKIPPED"
SNAPSHOT_ROW=""
BLOCKERS_ROW=""
SHADOW_ROW=""

if [[ -n "${POSTGRES_DSN:-}" && "$(have_psql; echo $?)" == "0" ]]; then
  SCHEMA_STATUS="OK"
  for relation in \
    "positions" \
    "transactions" \
    "execution_intents" \
    "portfolio_snapshots" \
    "position_marks" \
    "shadow_decision_trace" \
    "shadow_outcome_labels" \
    "idx_positions_one_active_per_pool"
  do
    exists="$(query_bool "SELECT to_regclass('public.${relation}') IS NOT NULL;")"
    if [[ "$exists" != "t" && "$exists" != "true" ]]; then
      SCHEMA_STATUS="MISSING:${relation}"
      break
    fi
  done

  SNAPSHOT_ROW="$(query_value "
    SELECT
      created_at,
      native_balance_wei,
      gas_reserve_wei,
      open_position_exposure_usd,
      pending_exposure_usd,
      submitted_private_exposure_usd,
      realized_pnl_usd,
      unrealized_pnl_usd
    FROM portfolio_snapshots
    ORDER BY created_at DESC
    LIMIT 1;
  ")"
  if [[ -n "$SNAPSHOT_ROW" ]]; then
    SNAPSHOT_STATUS="OK"
  else
    SNAPSHOT_STATUS="MISSING"
  fi

  BLOCKERS_ROW="$(query_value "
    SELECT
      COALESCE(stuck_tx_count,0),
      COALESCE(exit_failed_position_count,0),
      COALESCE(unreconciled_opening_count,0),
      COALESCE(unreconciled_opening_timeout_count,0)
    FROM portfolio_snapshots
    ORDER BY created_at DESC
    LIMIT 1;
  ")"

  SHADOW_ROW="$(query_value "
    SELECT
      COUNT(*),
      COALESCE(SUM(CASE WHEN label = 'win' THEN 1 ELSE 0 END),0),
      COALESCE(SUM(CASE WHEN label = 'loss' THEN 1 ELSE 0 END),0),
      COALESCE(SUM(CASE WHEN label = 'invalid' THEN 1 ELSE 0 END),0)
    FROM shadow_outcome_labels;
  ")"
fi

OVERALL="PASS"
if [[ "$CONFIG_STATUS" != "OK" || "$COMMIT_STATUS" != "OK" || "$SCHEMA_STATUS" != "OK" ]]; then
  OVERALL="FAIL"
fi
for name in "${REQUIRED_VARS[@]}"; do
  if [[ "${ENV_STATUS[$name]}" != "OK" ]]; then
    OVERALL="FAIL"
  fi
done
# Readiness precedence is strict: once FAIL is reached, later soft issues cannot
# downgrade it to WARN.
if [[ "$SNAPSHOT_STATUS" != "OK" && "$OVERALL" != "FAIL" ]]; then
  OVERALL="WARN"
fi

cat >"$REPORT_PATH" <<EOF
# Live Readiness 报告

- 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- 总结: ${OVERALL}
- 当前 commit: \`${CURRENT_COMMIT}\`
- 期望 commit: \`${EXPECTED_COMMIT:-未指定}\`
- commit 状态: ${COMMIT_STATUS}
- 配置文件: \`${CONFIG_PATH}\`
- 配置状态: ${CONFIG_STATUS}

## 必需环境变量

| 变量 | 状态 |
| --- | --- |
$(for name in "${REQUIRED_VARS[@]}"; do printf '| `%s` | %s |\n' "$name" "${ENV_STATUS[$name]}"; done)

## Schema 检查

- PostgreSQL 可用: $( [[ -n "${POSTGRES_DSN:-}" ]] && echo YES || echo NO )
- psql 可用: $( have_psql && echo YES || echo NO )
- schema 状态: ${SCHEMA_STATUS}

## 最新 Snapshot

- snapshot 状态: ${SNAPSHOT_STATUS}
- 最新行:

\`\`\`
${SNAPSHOT_ROW:-<none>}
\`\`\`

- blocker 计数:

\`\`\`
${BLOCKERS_ROW:-<none>}
\`\`\`

## Shadow Outcome

\`\`\`
${SHADOW_ROW:-<none>}
\`\`\`

## 建议

1. 先确认 schema guard 和最新 snapshot 连续写入正常。
2. 如果 blocker 计数非零，先处理 stuck / exit_failed / unreconciled opening。
3. 只有在 shadow outcome 样本足够且 gas 后净收益不为负时，再考虑 tiny canary。
EOF

printf '[live-readiness] report=%s overall=%s\n' "$REPORT_PATH" "$OVERALL"

if [[ "$OVERALL" == "FAIL" ]]; then
  exit 2
fi
