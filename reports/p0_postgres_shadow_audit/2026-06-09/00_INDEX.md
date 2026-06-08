# P0 Postgres/Supabase Shadow Audit — Index

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`
- **stage status**: WARN
- **branch**: `feat/supabase-postgres-deployment`
- **commit_before**: `ed84970`
- **audited_at_utc**: `2026-06-09T00:00:00Z`
- **auditor**: audit subagent (read-only, no code/migration/config changes)

## File list

| # | 文件 | 内容 | 段落 |
|---|---|---|---|
| 1 | `00_INDEX.md` | 本索引 | — |
| 2 | `01_EXECUTIVE_SUMMARY_CN.md` | 中文 executive summary + 8 P0 + 2 P1 blockers | §1-3 |
| 3 | `02_SCHEMA_CODE_DRIFT_AUDIT.md` | schema-vs-code drift, 8 个 P0 + 3 个 P1 drift | §1-7 |
| 4 | `03_DEPLOYMENT_RUNNABILITY_AUDIT.md` | systemd / env / config / runbook alignment | §1-5 |
| 5 | `04_CI_AND_TEST_GAP_AUDIT.md` | CI / -race / postgres tests / migration tests | §1-6 |
| 6 | `05_FIX_PLAN_P0_PG_02.md` | P0-PG-02 修复计划 + 5 sub-stages | §1-7 |
| 7 | `FINAL_AUDIT_VERDICT.json` | 主 verdict, top 10 blockers, ready_for_p0_pg_02_fix | — |

## 章节速查

- **§1 Executive Summary** — 整体风险等级 (P0 高), 8 P0 + 2 P1, 是否 ready_for_p0_pg_02_fix.
- **§2 Schema Drift** — 8 个 P0 drift (3 missing tables, 1 file numbering gap, 1 chain type inconsistency, 1 shadow unit missing EnvironmentFile, 1 test schema divergence, 1 no-Go-migration-runner, 1 non-idempotent migration).
- **§3 Deployment** — lpbot-shadow.service vs canary.service 不对称, env vars vs systemd manager.
- **§4 CI** — 无 -race, 无 postgres property tests, 无 migration parse / apply tests, 无 schema-code drift test.
- **§5 Fix Plan** — P0-PG-02 拆 5 sub-tasks (A: add 3 missing migrations, B: consolidate in-Go CREATE TABLE, C: chain type align, D: lpbot-shadow.service EnvironmentFile, E: migration runner + embed).

## 报告数据点 (1 句话)

- 整体风险等级: **P0 (高)**
- 是否适合进入 P0-PG-02: ✅ **YES** (ready_for_p0_pg_02_fix=true)
- 8 个 P0 必修: 3 missing-table migrations + 1 file numbering gap + 1 chain type inconsistency + 1 systemd EnvironmentFile + 1 test schema divergence + 1 no-Go-migration-runner
- 2 个 P1 必修: 000004 non-idempotent + no -race in CI
- 严禁 (维持): R1 12h PAUSE, R2 LOCKED, canary/live LOCKED

## 报告落盘路径

```
/opt/lpbot/lp-bot-v3-origin-check/reports/p0_postgres_shadow_audit/2026-06-09/
├── 00_INDEX.md
├── 01_EXECUTIVE_SUMMARY_CN.md
├── 02_SCHEMA_CODE_DRIFT_AUDIT.md
├── 03_DEPLOYMENT_RUNNABILITY_AUDIT.md
├── 04_CI_AND_TEST_GAP_AUDIT.md
├── 05_FIX_PLAN_P0_PG_02.md
└── FINAL_AUDIT_VERDICT.json
```

## 报告来源

- 用户委托: P0-PG-01 audit, schema-to-code consistency for Postgres/Supabase shadow deployment
- 审计方式: Read-only (无代码修改, 无 migration 修改, 无 DSN/token 密钥泄露, 无 docker compose up, 无外部 DB 连接)
- 审计输入: 12 postgres migrations + 8 postgres adapter .go files + cmd/lpbot/*.go + 2 systemd units + 4 .toml configs + 6 .env*.example + 1 migration shell script + CI workflow + Makefile
- 报告承诺: 不修改代码, 不泄露 DSN/token/密钥, 不进入 R1/R2/canary/live, 不启动 shadow/long-horizon

## 报告使用建议

1. **P0-PG-02 engineer** 优先修 8 个 P0 blockers (per 05_FIX_PLAN_P0_PG_02.md)
2. **P0-PG-04/05 owner** 加 migration parse / apply test + -race + postgres property tests
3. **架构决策** (per 02 §7): chain 跨表 join 用 INT 还是 TEXT, migration runner 用 goose 还是自己写
4. **PR review** 任何对 migrations/postgres/*.sql 的 PR 必查 schema-vs-code drift test 通过

---

报告版本: 2026-06-09. 报告作者: audit subagent (per user request).
审计对象: LP-bot postgres adapter + shadow deployment @ `ed84970` (branch `feat/supabase-postgres-deployment`).
