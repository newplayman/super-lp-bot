# P0 Postgres/Supabase Shadow Audit — Executive Summary (CN)

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`
- **status**: **WARN** (ready for P0-PG-02 fix)
- **branch**: `feat/supabase-postgres-deployment`
- **commit_before**: `ed84970` (含 R1 12h PAUSE_AND_FREEZE stage)
- **audited_at_utc**: `2026-06-09T00:00:00Z`

## 0. 一句话

P0-PG-01 schema-to-code consistency audit 完成. 8 个 P0 + 2 个 P1 blockers 找到, 全部 fixable in P0-PG-02. **不**修改任何 code / migration / config; **不**进入 R1 / R2 / canary / live; **不**启动 shadow smoke. R1 12h PAUSE 仍维持 (per `ed84970`).

## 1. 整体风险评级

**P0 (高)**: lpbot-shadow 当前**无法在 fresh VPS Postgres 上成功启动并通过 live schema guard**. 主要障碍是 (a) `shadow_decision_trace` / `shadow_position_marks` / `shadow_exit_*` 表不在任何 migration (runtime in-Go CREATE TABLE 兜底), (b) migration 文件编号 gap (000010 → 000012), (c) chain 列类型跨表不一致 (INT vs TEXT), (d) `lpbot-shadow.service` 缺 `EnvironmentFile=.env.postgres`, (e) Postgres integration test 自我 skip 除非 docker 可用.

## 2. Top 10 Blockers (8 P0 + 2 P1)

| # | 严重度 | ID | 标题 |
|---|---|---|---|
| 1 | **P0** | BLK-PG-01 | Missing migration: `shadow_decision_trace` |
| 2 | **P0** | BLK-PG-02 | Missing migration: `shadow_position_marks` |
| 3 | **P0** | BLK-PG-03 | Missing migration: `shadow_exit_decisions` / `shadow_exit_actions` |
| 4 | **P0** | BLK-PG-04 | Migration file numbering gap: 000010 → 000012 (no 000011) |
| 5 | **P0** | BLK-PG-05 | Chain column type inconsistency (TEXT vs INTEGER across tables) |
| 6 | **P0** | BLK-PG-06 | `lpbot-shadow.service` missing `EnvironmentFile=.env.postgres` |
| 7 | **P0** | BLK-PG-07 | `TestPostgresAdapter_DockerIntegration_RoundTrip` is skip-gated + schema-divergent |
| 8 | **P0** | BLK-PG-08 | No Go migration runner / no embed / no goose dependency; psql in shell |
| 9 | P1 | BLK-PG-09 | `000004_transactions_timestamp_cleanup` is non-idempotent |
| 10 | P1 | BLK-PG-10 | No `-race` in CI or Makefile |

详见 `02_SCHEMA_CODE_DRIFT_AUDIT.md` §5, `03_DEPLOYMENT_RUNNABILITY_AUDIT.md` §4, `04_CI_AND_TEST_GAP_AUDIT.md` §5.

## 3. R1 / R2 / canary / live 状态 (维持)

| 项目 | 状态 |
|---|---|
| R1 12h full wallclock research thread | **PAUSED** (per `ed84970`, 7 文件) |
| R2 (actual fee accrual) | **LOCKED** (actual_fee_data_available=false, fee_proxy_only=true) |
| canary / live / paper | **LOCKED** (can_run_probe_now=false, tiny_canary_allowed=no) |
| edge_proven | "no" |
| LP strategy research freeze | FROZEN (per `docs/LPBOT_RESEARCH_STATUS_CN.md`) |
| pkill -f | NOT USED |
| merge main / dev | NOT DONE |
| paid RPC / paid indexer | NOT USED |
| real secret committed | NOT DONE |

## 4. 严禁 (本 audit stage)

- ❌ 不修改 code / migration / config
- ❌ 不运行 psql / apply migrations to real DB
- ❌ 不 docker compose up
- ❌ 不连 Supabase / 任何 external service
- ❌ 不启动 lpbot-shadow / 长跑
- ❌ 不连 wallet / keypair / signer
- ❌ 不发 tx / mint / add liquidity
- ❌ 不接 paid RPC
- ❌ 不写真实 secret
- ❌ 不 merge main / dev
- ❌ 不使用 pkill -f
- ❌ 不修改 R1 reports / data dirs
- ❌ 不 reopen R1
- ❌ 不修 supervisor
- ❌ 不启动 12h / 13h / 24h / 48h / 72h / 7d
- ❌ 不进入 R2
- ❌ 不 probe / canary / live / paper
- ❌ 不直接 ALTER 线上 DB
- ❌ 不运行 destructive migration

## 5. 报告使用建议 (per 5 PGs sub-tasks)

| 阶段 | 负责 fix | 估时 (人天) |
|---|---|---|
| P0-PG-02-A | Add 3 missing-table migrations + 000011 placeholder fix | 1-2 |
| P0-PG-02-B | Consolidate 2 in-Go CREATE TABLE statements (decision_trace.go, position_mark.go) into migrations | 0.5 |
| P0-PG-02-C | Chain type alignment (decide INT vs TEXT, write migration to align) | 1 |
| P0-PG-02-D | `lpbot-shadow.service` add `EnvironmentFile=.env.postgres` | 0.25 |
| P0-PG-02-E | Go migration runner + embed.FS (or goose import) + checksum + ordering | 2-3 |
| P0-PG-04 (CI) | Migration parse / apply tests in CI, schema-code drift test, postgres property tests | 1-2 |
| P0-PG-05 (CI) | -race in CI / Makefile | 0.25 |

详见 `05_FIX_PLAN_P0_PG_02.md` §1-7.

## 6. 一句话

P0-PG-01 审计 8 P0 + 2 P1 blockers found, all fixable in P0-PG-02. ready_for_p0_pg_02_fix=true. 不动 code / migration / config. R1 PAUSE 维持, R2 LOCKED 维持, canary/live LOCKED 维持. Recommended next stage: **LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DRIFT_FIX_V1**.
