# P0-PG-02E — Migration Audit

- **stage**: `LP_BOT_ENGINEERING_P0_PG_02E_MIGRATION_RUNNER_IDEMPOTENCY_V1`
- **run_id**: `20260609_060000`
- **base_commit**: `a22eb86`
- **branch**: `feat/supabase-postgres-deployment`
- **workdir**: `/opt/lpbot/lp-bot-v3`

## 1. Audit 范围

每 migration: transaction-safety, idempotency, retry-safety。15 个 migration 在 `migrations/postgres/`:

```
000001_init_schema.sql
000002_canary_state.sql
000003_pool_runtime_columns.sql
000004_transactions_timestamp_cleanup.sql
000005_positions_runtime_metadata.sql
000006_active_position_uniqueness.sql
000007_execution_intents.sql
000008_portfolio_snapshots.sql
000009_pnl_v1_and_position_marks.sql
000010_shadow_outcome_labels.sql
000011_shadow_decision_trace.sql
000012_shadow_outcome_repaired_v2.sql
000013_shadow_position_marks.sql
000014_shadow_exit_tables.sql
000015_chain_text_alignment.sql
```

## 2. Per-migration audit

| Migration | DDL lines | DML lines | Transaction-safe? | Idempotent? | Notes |
|-----------|-----------|-----------|------------------|-------------|-------|
| 000001_init_schema | 22 | 0 | ✓ (`-- +goose StatementBegin/End`) | ✓ (`CREATE TABLE IF NOT EXISTS` × 14, `CREATE INDEX IF NOT EXISTS`, etc.) | All DDL is idempotent. |
| 000002_canary_state | 5 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 4) | |
| 000003_pool_runtime_columns | 1 | 0 | ✓ | ✓ (`ADD COLUMN IF NOT EXISTS` × 5) | Single ALTER TABLE statement, 5 columns. |
| **000004_transactions_timestamp_cleanup** | 0 | 1 | ✓ | ⚠️ (see below) | **ONLY non-idempotent migration**. |
| 000005_positions_runtime_metadata | 3 | 0 | ✓ | ✓ (`ADD COLUMN IF NOT EXISTS` × 3) | |
| 000006_active_position_uniqueness | 2 | 0 | ✓ | ✓ (`CREATE UNIQUE INDEX IF NOT EXISTS`) | Partial unique index with WHERE clause. |
| 000007_execution_intents | 5 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 4) | |
| 000008_portfolio_snapshots | 3 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 2) | |
| 000009_pnl_v1_and_position_marks | 22 | 0 | ✓ | ✓ (`ADD COLUMN IF NOT EXISTS` × 17, `IF NOT EXISTS` × 15) | |
| 000010_shadow_outcome_labels | 5 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 4) | |
| 000011_shadow_decision_trace | 9 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 6) | |
| 000012_shadow_outcome_repaired_v2 | 6 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 5) | |
| 000013_shadow_position_marks | 5 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 3) | |
| 000014_shadow_exit_tables | 9 | 0 | ✓ | ✓ (`IF NOT EXISTS` × 6) | |
| 000015_chain_text_alignment | 42 | 8 | ✓ | ✓ (`ADD COLUMN IF NOT EXISTS` × 9, etc.) | Recreates idx_positions_one_active_per_pool at end. |

## 3. 000004 详细风险点

```sql
-- +goose Up
-- +goose StatementBegin

UPDATE transactions
SET
    created_at = CASE
        WHEN created_at > 0 AND created_at < 2000000000 THEN created_at * 1000
        ELSE created_at
    END,
    updated_at = CASE
        WHEN updated_at > 0 AND updated_at < 2000000000 THEN updated_at * 1000
        ELSE updated_at
    END,
    broadcast_at = CASE
        WHEN broadcast_at > 0 AND broadcast_at < 2000000000 THEN broadcast_at * 1000
        ELSE broadcast_at
    END,
    block_number = CASE
        WHEN block_number > 1000000000 THEN NULL
        ELSE block_number
    END;

-- +goose StatementEnd
```

### 风险 1: 部分失败一致性

如果 UPDATE 在更新 4 列过程中被中断（client disconnect, OOM kill, network drop），会有部分列已 × 1000、部分列未 × 1000 的混合状态。

- **`created_at`**: 如果 × 1000 (e.g. 1700000000 → 1700000000000) 而 `updated_at` 未 (still 1700000000)，后续依赖 created_at > updated_at 的查询会返回异常
- **`block_number`**: 如果已经 SET NULL (corrupted value 覆盖) 而其他列未 × 1000，audit log 会丢失旧的 block_number

### 风险 2: 重复执行幂等性

第二次执行 000004:
- `created_at < 2000000000` 现在不再为 true (因为第一次已经 × 1000)，所以 × 1000 不会再发生
- 第二次的 CASE 走 ELSE branch，**保持原值**不变

✓ 第二次执行是 safe (no double-multiplication)，因为 CASE 条件天然 idempotent。

### 风险 3: 跨 migration partial 状态

如果 000004 在事务中失败，事务会整体 rollback（因为 `-- +goose StatementBegin/End` 加上 Postgres 的 DDL implicit transaction）。**所以单 migration 的 partial 状态被事务保护**。

但是如果 client 端在事务 COMMIT 之前 disconnect 了呢？
- Postgres 默认行为: client disconnect → 当前事务自动 rollback
- 所以这种情况下 000004 整体失败，schema_migrations 不记录

✓ 单个 migration 的事务模型本身是 partial-failure-safe。

## 4. 决策: 不修改 000004 SQL, 改为 runner-level 保护

**理由**:
- 000004 已被应用在 0 production DBs (per the freeze; LP strategy research is PAUSED)
- 该 migration 本身的 UPDATE 是 idempotent (CASE WHEN 条件天然防止 double-multiplication)
- 风险 1 (partial failure) 已经被 per-migration transaction 覆盖 (Postgres 自动 rollback)
- 风险 2 (re-execution) 不存在 (CASE 天然 idempotent)
- 风险 3 (client disconnect) 已经被 transaction rollback 覆盖

**修改 000004 的潜在风险**:
- 如果有人在 v1 DB 上已应用 000004 并记录 checksum=hash_v1, 然后我们改 000004 内容, checksum 会变, runner 会 refuse to proceed
- 即使是"修"成 idempotent, 也会破坏 backward compatibility

**结论**: 不修改 000004 SQL file. 改为提供 runner-level 三层保护:

### 4.1 保护 1: Transaction-per-migration

在 Go runner 中，每个 migration 独立 `BeginTx` → `ExecContext(upSQL)` → `INSERT schema_migrations` → `Commit`. 任何错误触发 `Rollback` 并停止后续 migration. **已实现** (TestMigrator_PerMigrationTransactionRollback 验证).

### 4.2 保护 2: Checksum tracking

每个 applied migration 记录 SHA256 of file content. Re-running apply 时, 验证每个 applied row 的 checksum 与当前 file SHA256 一致; 不一致 refuse to proceed (避免在已应用的 migration 上重放可能不兼容的 SQL). **已实现** (TestMigrator_ChecksumMismatchRefuses 验证).

### 4.3 保护 3: Legacy backfill

如果 schema_migrations row 有 `checksum=''` (legacy pre-Go runner), 第一次 Go runner 跑时会用当前 file SHA256 backfill. 后续 run 用真实 checksum 验证. **已实现** (TestMigrator_LegacyDB_BackfillOnFirstApply 验证).

## 5. 是否可以安全修改旧 migration?

**不是** (per 上述分析). 改旧 migration 的风险:
- 破坏已经在 v1 DB 上应用 000004 的 checksum
- 引入 partial-failure 风险 (修改过程中可能引入 syntax error)

**替代方案** (本 stage 采用):
- 保留 000004 SQL 不动
- 在 runner 层提供三层 protection (trans 4.1, checksum 4.2, legacy backfill 4.3)
- 测试覆盖三种 DB state: fresh DB / partially-applied DB / already-applied DB

## 6. 三种 DB state 测试覆盖

| DB state | Test | 行为 | Result |
|----------|------|------|--------|
| Fresh DB | TestMigrator_ApplyOnFreshDB | DROP SCHEMA + Apply → 15 applied | PASS |
| Partially-failed (000001 OK, 000002 broken) | TestMigrator_PerMigrationTransactionRollback | Apply 2 migrations, 2nd fails mid-statement → 000001 applied, 000002 NOT applied, t2 NOT exists | PASS |
| Already-applied | TestMigrator_ReRunIsNoOp | Apply 15 → Apply again → all 15 skipped, 0 applied | PASS |
| Legacy (checksum='') | TestMigrator_LegacyDB_BackfillOnFirstApply | Pre-populate legacy row → Apply → checksum filled, no re-apply | PASS |
| File content changed post-apply | TestMigrator_ChecksumMismatchRefuses | Apply → mutate file → Apply again → refuse with checksum-mismatch error | PASS |

## 7. 一句话

15 个 migration 全部有 `-- +goose StatementBegin/End` 保护. 14 个完全 idempotent (`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS`). 000004 本身 CASE 条件天然 idempotent; 部分失败被 transaction 保护; 重复执行不会 double-multiply. 不修改 000004 SQL, 改为 Go runner 提供三层 protection (transaction + checksum + legacy backfill). 5 个 integration test 覆盖 fresh / partially-failed / already-applied / legacy / file-changed 五种 DB state, 全部 PASS.
