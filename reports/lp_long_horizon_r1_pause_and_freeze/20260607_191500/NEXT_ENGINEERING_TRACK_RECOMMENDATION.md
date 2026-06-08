# R1 12h Full Wallclock — Next Engineering Track Recommendation (CN)

- **stage**: `LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1`
- **status**: PAUSED
- **source_run_id**: 20260607_191500
- **review_commit**: b46f52e
- **recommended_next_engineering_track**: **`P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1`**

## 0. 一句话

R1 12h full wallclock research thread **PAUSED** (PARTIAL verdict + supervisor 拓扑结构性 off-by-one). R1 阶段不再追求 edge claim. 当前 LP-bot 工程主线仍有多个 P0 / P1 缺口. 推荐 redirect engineering work 到 **`P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1`**, 这与 R1 research thread **独立**, 不会触发任何 forbidden action, 也不会隐式 unlock R2 / canary / live.

## 1. 为什么 redirect 到 engineering

R1 research thread 当前状态:
- 唯一一次 12h full wallclock attempt (v3, RUN_ID 20260607_191500) = honest PARTIAL
- duration 不到 12h 是 supervisor 拓扑结构性问题, 需要 code change
- R2 仍 LOCKED (actual_fee_data_available=false, fee_proxy_only=true)
- edge_proven=no
- can_run_probe_now=false, tiny_canary_allowed=no
- 短期 (< 2-4 周) 内, 不太可能突破 R1 12h 阈值 + R2 actual fee 闭环

LP-bot 工程主线状态 (per CLAUDE.md, README, recent commits):
- branch `feat/supabase-postgres-deployment` 暗示 Postgres 迁移是 in-flight
- 但当前工程缺口: Postgres/Supabase schema-to-code 一致性, shadow deployment 可运行性, CI/migration tests, R2 actual fee accrual, canary/live freeze reopen
- 这些工程缺口是 **通往** 任何 future R1 PASS / R2 entry / canary / live 的 **必要前置**
- 不修这些, 即便 R1 supervisor fix + R1 12h PASS + R2 actual fee 闭环, 仍没法走到 small live probe

**结论**: R1 research thread pause 期间, engineering 才是 leverage 最高的 work stream. R1 不动, engineering 推.

## 2. P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1 范围

### 2.1 目标

修复 Postgres/Supabase 部署相关 P0 工程缺口, 让 `bin/lpbot-shadow` 在 Postgres backend 上可运行, 并把 schema 一致性 / migration test 纳入 CI.

### 2.2 子任务 (P0 级别)

| ID | 子任务 | 描述 | 估时 (人天) |
|---|---|---|---|
| P0-PG-01 | Postgres schema-to-code consistency audit | 对比 `migrations/postgres/*.sql` vs `internal/adapters/store/postgres/*.go` 字段映射, 找 drift | 2-3 |
| P0-PG-02 | Migration drift fix | 修 audit 发现的 drift; 新 migration 文件; 不要直接 ALTER 现存 table | 1-3 |
| P0-PG-03 | Shadow mode end-to-end smoke | `bin/lpbot-shadow` + Postgres backend 起得来, 跑一次短 shadow cycle (e.g. 30 min) | 2-4 |
| P0-PG-04 | Migration tests in CI | 加 `make test-migration` / `make test-postgres` target, CI 跑 | 1-2 |
| P0-PG-05 | Stronger CI for Postgres path | 跑 `golangci-lint` + `go test -race -tags=shadow` + 短 shadow cycle | 1-2 |
| P0-PG-06 | README + runbook 更新 | `docs/runbooks/postgres-shadow-deployment.md`; `.env.postgres.example` review | 1 |

**总估时**: 8-15 人天 (1 个工程师, full-time, 2-3 周)

### 2.3 不在范围 (out of scope)

- ❌ R1 12h supervisor fix (per `SUPERVISOR_FIX_OPTIONS_CN.md`)
- ❌ R2 actual fee accrual (LOCKED, needs freeze reopen)
- ❌ canary / live / small live probe (LOCKED)
- ❌ 修改 `docs/LPBOT_RESEARCH_STATUS_CN.md` 把 LP strategy research 从 FROZEN 改到 active
- ❌ merge main / dev
- ❌ 接 paid RPC / paid indexer

### 2.4 验收标准

- `make audit-consistency` 干净
- `make test` 干净
- `make test-property` 干净
- `make build-shadow` 干净
- `bin/lpbot-shadow --config=configs/config.shadow.toml` 在 Postgres backend 上能起得来
- 30-min shadow cycle: 启动 → 接 1 个 datasource → 收 ≥ 1 个 pool.scored → 写 store → 退出 rc=0
- 不发任何 tx, 不连 wallet, 不连 canary / live

## 3. 子任务之间的依赖

```
P0-PG-01 (audit) ──> P0-PG-02 (fix drift)
                        │
                        v
                  P0-PG-03 (smoke) ──> P0-PG-04 (migration tests) ──> P0-PG-05 (CI)
                                                                              │
                                                                              v
                                                                        P0-PG-06 (docs)
```

串行依赖: 02 → 03 → 04 → 05 → 06. 01 是 input.

## 4. 与 R1 / R2 / canary / live 的关系

| 项目 | 与 P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1 关系 |
|---|---|
| R1 12h full wallclock | 独立, 互不影响. R1 PAUSED; P0 进行中. |
| R2 actual fee accrual | 独立, 仍 LOCKED. P0 完成 ≠ R2 自动 unlock. R2 需 freeze reopen. |
| canary / live / small live probe | 独立, 仍 LOCKED. P0 完成 ≠ canary / live 自动 unlock. |
| edge_proven | 仍 "no". P0 完成 ≠ edge. |
| supervisor fix | 独立. P0 完成 ≠ supervisor 修好. |
| PAUSE 决策 | 不变. R1 仍 PAUSED, 任何 reopen 需 user 显式 + 6 hard conditions. |
| forbidden actions 22 项 | 仍 locked. P0 不触发任何 FAL-01..FAL-22. |

## 5. 推荐的分阶段 (sub-stages) 命名

如果 user 接受 redirect, 推荐的 stage 命名:

1. `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1` — 跑 P0-PG-01
2. `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DRIFT_FIX_V1` — 跑 P0-PG-02
3. `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_SMOKE_V1` — 跑 P0-PG-03 (短 shadow cycle)
4. `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_CI_V1` — 跑 P0-PG-04 + P0-PG-05
5. `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DOCS_V1` — 跑 P0-PG-06

每 stage 独立 artifact, 独立 review, 独立 commit.

## 6. 一句话

R1 research thread **PAUSED**, 推荐 redirect 到 **`P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1`** (8-15 人天, 2-3 周). 这与 R1 / R2 / canary / live **完全独立**, 不触发任何 forbidden action, 不隐式 unlock 任何 LOCKED field. Engineering 完成后, future R1 / R2 / canary / live 才有更稳的基础.
