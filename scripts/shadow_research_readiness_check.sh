#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${LPBOT_SHADOW_RESEARCH_CONFIG:-configs/config.shadow.toml}"
REPORT_PATH="${LPBOT_SHADOW_RESEARCH_REPORT_PATH:-SHADOW_RESEARCH_READINESS_CN.md}"
EXPECTED_COMMIT="${LPBOT_SHADOW_EXPECT_COMMIT:-}"
MIN_GOOSE_VERSION="${LPBOT_SHADOW_MIN_GOOSE_VERSION:-10}"

load_env() {
  cd "$ROOT_DIR"
  if [[ -f ./.env.postgres ]]; then set -a; . ./.env.postgres; set +a; fi
  if [[ -f ./.env.shadow ]]; then set -a; . ./.env.shadow; set +a; fi
  if [[ -f ./.env.dashboard ]]; then set -a; . ./.env.dashboard; set +a; fi
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
)

declare -A ENV_STATUS
for name in "${REQUIRED_VARS[@]}"; do
  ENV_STATUS["$name"]="$(check_env_var "$name")"
done

SCHEMA_STATUS="SKIPPED"
GOOSE_STATUS="SKIPPED"
DB_WRITE_STATUS="SKIPPED"
RELATION_ROWS=""
GOOSE_VERSION_ROW=""
DECISION_TRACE_ROW=""
POSITION_MARK_ROW=""
OUTCOME_ROW=""
HORIZON_ROW=""

if [[ -n "${POSTGRES_DSN:-}" ]] && have_psql; then
  SCHEMA_STATUS="OK"

  if [[ "$(query_bool "SELECT to_regclass('public.goose_db_version') IS NOT NULL;")" =~ ^(t|true)$ ]]; then
    GOOSE_VERSION_ROW="$(query_value "SELECT COALESCE(MAX(version_id),0) FROM goose_db_version WHERE is_applied = TRUE;")"
    if [[ -n "$GOOSE_VERSION_ROW" && "$GOOSE_VERSION_ROW" =~ ^[0-9]+$ && "$GOOSE_VERSION_ROW" -ge "$MIN_GOOSE_VERSION" ]]; then
      GOOSE_STATUS="OK"
    else
      GOOSE_STATUS="OUTDATED:${GOOSE_VERSION_ROW:-0}"
    fi
  else
    GOOSE_STATUS="MISSING:goose_db_version"
  fi

  for relation in \
    "shadow_decision_trace" \
    "shadow_position_marks" \
    "shadow_outcome_labels"
  do
    exists="$(query_bool "SELECT to_regclass('public.${relation}') IS NOT NULL;")"
    if [[ "$exists" != "t" && "$exists" != "true" ]]; then
      SCHEMA_STATUS="MISSING:${relation}"
      break
    fi
  done

  DB_WRITE_STATUS="OK"
  if ! psql "$POSTGRES_DSN" -X -A -t -c "SELECT 1;" >/dev/null 2>&1; then
    DB_WRITE_STATUS="QUERY_FAILED"
  fi

  RELATION_ROWS="$(query_value "
    SELECT
      COALESCE((SELECT count(*) FROM shadow_decision_trace),0),
      COALESCE((SELECT count(*) FROM shadow_position_marks),0),
      COALESCE((SELECT count(*) FROM shadow_outcome_labels),0);
  ")"

  DECISION_TRACE_ROW="$(query_value "
    SELECT
      COALESCE(MAX(created_at),0),
      COALESCE(COUNT(*),0)
    FROM shadow_decision_trace;
  ")"

  POSITION_MARK_ROW="$(query_value "
    SELECT
      COALESCE(MAX(mark_time),0),
      COALESCE(COUNT(*),0)
    FROM shadow_position_marks;
  ")"

  OUTCOME_ROW="$(query_value "
    SELECT
      COALESCE(COUNT(*),0),
      COALESCE(SUM(CASE WHEN label = 'win' THEN 1 ELSE 0 END),0),
      COALESCE(SUM(CASE WHEN label = 'loss' THEN 1 ELSE 0 END),0),
      COALESCE(SUM(CASE WHEN label = 'invalid' THEN 1 ELSE 0 END),0)
    FROM shadow_outcome_labels;
  ")"

  HORIZON_ROW="$(query_value "
    SELECT
      horizon,
      COUNT(*),
      COALESCE(SUM(CASE WHEN label = 'invalid' THEN 1 ELSE 0 END),0)
    FROM shadow_outcome_labels
    GROUP BY horizon
    ORDER BY horizon;
  ")"
fi

OVERALL="PASS"
if [[ "$CONFIG_STATUS" != "OK" || "$COMMIT_STATUS" != "OK" || "$SCHEMA_STATUS" != "OK" || "$GOOSE_STATUS" != "OK" || "$DB_WRITE_STATUS" != "OK" ]]; then
  OVERALL="FAIL"
fi
for name in "${REQUIRED_VARS[@]}"; do
  if [[ "${ENV_STATUS[$name]}" != "OK" ]]; then
    OVERALL="FAIL"
  fi
done

cat >"$REPORT_PATH" <<EOF
# Shadow Research Readiness 报告

- 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- 总结: ${OVERALL}
- 当前 commit: \`${CURRENT_COMMIT}\`
- 期望 commit: \`${EXPECTED_COMMIT:-未指定}\`
- commit 状态: ${COMMIT_STATUS}
- 配置文件: \`${CONFIG_PATH}\`
- 配置状态: ${CONFIG_STATUS}

## 研究链必需环境变量

| 变量 | 状态 |
| --- | --- |
$(for name in "${REQUIRED_VARS[@]}"; do printf '| `%s` | %s |\n' "$name" "${ENV_STATUS[$name]}"; done)

## 数据库与迁移

- PostgreSQL 可用: $( [[ -n "${POSTGRES_DSN:-}" ]] && echo YES || echo NO )
- psql 可用: $( have_psql && echo YES || echo NO )
- goose 版本状态: ${GOOSE_STATUS}
- goose 已应用最大版本: ${GOOSE_VERSION_ROW:-<none>}
- schema 状态: ${SCHEMA_STATUS}
- 基本查询状态: ${DB_WRITE_STATUS}

## 研究表计数

\`\`\`
${RELATION_ROWS:-<none>}
\`\`\`

格式: \`shadow_decision_trace_count<TAB>shadow_position_marks_count<TAB>shadow_outcome_labels_count\`

## 最新研究活动

- 最新 decision trace:

\`\`\`
${DECISION_TRACE_ROW:-<none>}
\`\`\`

- 最新 shadow position mark:

\`\`\`
${POSITION_MARK_ROW:-<none>}
\`\`\`

- shadow outcome 汇总:

\`\`\`
${OUTCOME_ROW:-<none>}
\`\`\`

格式: \`total<TAB>win<TAB>loss<TAB>invalid\`

- horizon 分布:

\`\`\`
${HORIZON_ROW:-<none>}
\`\`\`

格式: \`horizon<TAB>count<TAB>invalid_count\`

## 结论

1. 本检查只服务于 shadow research，只验证只读研究链，不验证 live wallet / Flashbots / live 交易门禁。
2. 只有当 commit、基础 env、Postgres、迁移、研究表都通过时，才允许执行 shadow outcome backfill/report。
3. 如果 shadow outcome 样本仍为空，不代表失败，只表示需要继续积累 1h / 6h / 24h 样本。
EOF

printf '[shadow-research-readiness] report=%s overall=%s\n' "$REPORT_PATH" "$OVERALL"

if [[ "$OVERALL" == "FAIL" ]]; then
  exit 2
fi
