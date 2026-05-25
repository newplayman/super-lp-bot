#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_COMMIT="${LPBOT_VPS_EXPECT_COMMIT:-}"
CONFIG_PATH="${LPBOT_VPS_CONFIG_PATH:-configs/config.live.toml}"

cat <<EOF
# VPS Shadow Outcome 只读执行计划

本脚本只输出计划，不执行任何交易，不启动 live mint。

## 1. 对齐代码

cd ${ROOT_DIR}
git fetch origin
git checkout feat/supabase-postgres-deployment
git pull --ff-only
git rev-parse HEAD
# 期望 commit: ${EXPECTED_COMMIT:-<未指定>}

## 2. 本地/服务器自检

go test ./...
go test -tags live ./cmd/lpbot ./internal/adapters/broadcast/live ./internal/adapters/mev/flashbots-protect
bash -n scripts/live_readiness_check.sh

## 3. 数据库迁移与关系检查

# 先查看状态
goose -dir migrations/postgres postgres "\$POSTGRES_DSN" status
# 再执行迁移
goose -dir migrations/postgres postgres "\$POSTGRES_DSN" up

psql "\$POSTGRES_DSN" -c "SELECT to_regclass('public.shadow_outcome_labels');"
psql "\$POSTGRES_DSN" -c "SELECT to_regclass('public.execution_intents');"
psql "\$POSTGRES_DSN" -c "SELECT to_regclass('public.portfolio_snapshots');"
psql "\$POSTGRES_DSN" -c "SELECT to_regclass('public.position_marks');"
psql "\$POSTGRES_DSN" -c "SELECT to_regclass('public.idx_positions_one_active_per_pool');"

## 4. 只读 shadow 回填与报告

go run ./cmd/lpbot --config=${CONFIG_PATH} --shadow-outcomes-backfill --report-shadow-outcomes
./scripts/live_readiness_check.sh

## 5. 观察重点

- portfolio_snapshots 是否持续刷新
- shadow_outcome_labels 是否开始产生 1h / 6h / 24h 样本
- REPORT_SHADOW_OUTCOMES_CN.md 中 invalid_rate 是否过高
- high_score_vs_low_score 是否开始出现 better 信号

## 禁止项

- 不运行 --canary-mint
- 不运行 daemon live open
- 不发送任何真实交易
EOF
