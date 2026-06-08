# P0-PG-02 Schema Compatibility Report

- **stage**: `P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1`
- **run_id**: `20260608_181508`
- **base_commit**: `61f6621`
- **branch**: `feat/supabase-postgres-deployment`
- **workdir**: `/opt/lpbot/lp-bot-v3`
- **audit_copy**: `/opt/lpbot/lp-bot-v3-origin-check` (read-only, no edits)

## 1. 目标

确保 `migrations/postgres/*.sql` 与 `cmd/lpbot/main.go` 的 `loadLiveSchemaState` 守卫 + `internal/adapters/store/postgres/*.go` 仓库的字段访问一致. 任何 8 个 user spec 列出对象 (`positions`, `pools`, `transactions`, `execution_intents`, `portfolio_snapshots`, `position_marks`, `canary_events`, `shadow_decision_trace`, `idx_positions_one_active_per_pool`) 的字段缺失都补上.

## 2. 变更摘要

### 2.1 新增 `migrations/postgres/000011_shadow_decision_trace.sql`

补齐 live schema guard 强制要求但任何 migration 都未 CREATE 的表 `shadow_decision_trace`.

**来源**:
- `cmd/lpbot/main.go:821` 在 `loadLiveSchemaState` 把 `shadow_decision_trace` 列入 `required`
- `cmd/lpbot/decision_trace.go:55-95` 之前用 in-Go `CREATE TABLE IF NOT EXISTS` 兜底, 现在迁移为 migration 作为 source-of-truth
- `cmd/lpbot/canary_state.go:303` 是该表的 SELECT 消费者之一

**schema 内容**:
- 23 列: id, tick_time, trace_id, pool_id, pool_key, chain, protocol, score_total, score_json, selected, selected_rank, selection_reason, intent_open, intent_reason, chain_stage, chain_reason, pipeline_stage, pipeline_ok, pipeline_reason, final_action, position_id, tx_hash, created_at
- 3 indexes: `idx_shadow_decision_trace_created_at`, `idx_shadow_decision_trace_tick_time`, `idx_shadow_decision_trace_pool_id`
- 2 个 additive ALTER TABLE ADD COLUMN (chain_stage, chain_reason) — 兼容 in-Go CREATE TABLE 已经部署的实例

**goose 注释**:
- `-- +goose Up` / `-- +goose StatementBegin` ... `-- +goose StatementEnd` / `-- +goose Down`

### 2.2 现有 migration audit (no change required)

| 对象 | migration 状态 | 备注 |
|---|---|---|
| `positions.protocol` | ✅ 000005 ALTER ADD COLUMN | code 写: pos.Protocol (string); code 读: COALESCE(protocol, '') |
| `positions.open_tx_hash` | ✅ 000005 ALTER ADD COLUMN | code 写: pos.OpenTxHash; code 读: COALESCE(open_tx_hash, '') |
| `positions.metadata` | ✅ 000005 ALTER ADD COLUMN JSONB | code 写: defaultPositionMetadataJSON(pos.MetadataJSON); code 读: COALESCE(metadata::text, '{}') |
| `pools.liquidity` | ✅ 000003 ALTER ADD COLUMN TEXT | code 写: pool.Pool.Liquidity.String(); code 读: sql.NullString + MustDecimal |
| `pools.tick` | ✅ 000003 ALTER ADD COLUMN BIGINT | code 写: pool.Pool.Tick (int); code 读: sql.NullInt64 |
| `pools.tvl_usd` | ✅ 000003 ALTER ADD COLUMN TEXT | code 写: pool.Pool.TVLUSD.String(); code 读: sql.NullString + MustDecimal |
| `pools.vol_24h` | ✅ 000003 ALTER ADD COLUMN TEXT | code 写: pool.Pool.Vol24h.String(); code 读: sql.NullString + MustDecimal |
| `pools.fee_apr_24h` | ✅ 000003 ALTER ADD COLUMN TEXT | code 写: pool.Pool.FeeAPR24h.String(); code 读: sql.NullString + MustDecimal |
| `transactions.*` (23 cols) | ✅ 000001 CREATE | 字段一一对齐 |
| `execution_intents.*` (17 cols) | ✅ 000007 CREATE | 字段一一对齐 |
| `portfolio_snapshots.*` (15 cols + 4 ALTER) | ✅ 000008 + 000009 ALTER | 字段一一对齐 |
| `position_marks.*` (17 cols) | ✅ 000009 CREATE | 字段一一对齐 |
| `canary_events.*` (25 cols) | ✅ 000002 CREATE | 字段一一对齐 |
| `pnl_ledger.*` (10 cols + 10 ALTER) | ✅ 000001 + 000009 ALTER | 字段一一对齐 |
| `idx_positions_one_active_per_pool` | ✅ 000006 CREATE UNIQUE INDEX (partial) | code 期望 `WHERE status IN ('intended', 'approved', 'opening', 'open', 'exiting')` |

**结论**: 8 个 user spec 列出对象 + 1 个 index 全部对齐. 不需要改既有 migration. 只需要补 `shadow_decision_trace` (新加 000011).

## 3. 静态 schema compatibility test 结果

新 test `TestMigrationsSchemaCompatibility` (in `internal/adapters/store/postgres/migrate_test.go`):

```
$ go test ./internal/adapters/store/postgres/ -run TestMigrationsSchemaCompatibility -v
=== RUN   TestMigrationsSchemaCompatibility
--- PASS: TestMigrationsSchemaCompatibility (0.05s)
PASS
ok  	github.com/lpbot/lpbot/internal/adapters/store/postgres	0.094s
```

**测试覆盖**:
- 13 个必需表 (positions, transactions, execution_intents, portfolio_snapshots, position_marks, canary_events, pnl_ledger, shadow_decision_trace, pools, pool_score_history, risk_events, kill_switch_state, shadow_outcome_labels) 全部 CREATE
- 1 个必需 index (idx_positions_one_active_per_pool) 存在
- 9 个表的必需列 (10+ 列 per 表) 在 CREATE TABLE body 或 ALTER TABLE ADD COLUMN 中存在
- 支持 compact multi-column ALTER (000003 用 `ADD COLUMN IF NOT EXISTS x, ADD COLUMN IF NOT EXISTS y, ...`)

**未覆盖** (per audit 报告):
- `shadow_position_marks` / `shadow_exit_decisions` / `shadow_exit_actions` (in-Go CREATE, not in migration) — 留 P0-PG-02-A
- chain type 跨表一致性 (INT vs TEXT) — 留 P0-PG-02-C
- Go migration runner — 留 P0-PG-02-E

## 4. 已知 gap (per P0-PG-01 audit 报告, 本 stage 不修)

| Gap | Severity | 状态 | 修在 |
|---|---|---|---|
| `shadow_position_marks` 不在 migration | P0 | Not addressed this stage | P0-PG-02-A |
| `shadow_exit_decisions` / `shadow_exit_actions` 不在 migration | P0 | Not addressed this stage | P0-PG-02-A |
| Migration 000010 → 000012 编号 gap | P0 | Not investigated this stage (git log) | P0-PG-02-A |
| chain type 跨表不一致 | P0 | Not addressed this stage | P0-PG-02-C |
| 无 Go migration runner | P0 | Not addressed this stage | P0-PG-02-E |
| 000004 non-idempotent | P1 | Not addressed this stage | P0-PG-02-E |
| 无 -race in CI | P1 | Not addressed this stage | P0-PG-05 |

**Rationale**: User spec 限定本 stage 只处理 user spec 列出的 8 个对象 + 1 index. 其他 P0 留 future stages.

## 5. 一句话

新加 `migrations/postgres/000011_shadow_decision_trace.sql` 补齐 live schema guard 强制要求的 `shadow_decision_trace` 表. 既有 migration 中 8 个 user spec 列出对象 + 1 index 全部字段对齐, 不需要改. 静态 schema compatibility test 确认所有必需表/列/index 在 migration 中存在. 6 个其他 P0 gap (shadow_position_marks, shadow_exit_*, chain type, migration runner, etc.) 留 P0-PG-02 follow-up stages.
