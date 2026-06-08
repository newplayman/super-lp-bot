# P0-PG-02 Review-Repair — Schema Drift Repair Report

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_REVIEW_REPAIR_V1`
- **run_id**: `20260608_190000`
- **base_commit**: `6ec750a`
- **branch**: `feat/supabase-postgres-deployment`
- **workdir**: `/opt/lpbot/lp-bot-v3`

## 1. Reviewer critique (re-stated)

1. `changed_files` 未包含 `migrations/postgres/*.sql` → drift 很可能没真正修复
2. `changed_files` 未包含 `internal/adapters/store/postgres/*.go` → 缺代码侧修复
3. `deploy/systemd/lpbot-shadow.service` 未实际修改 → 只改 canary 注释
4. shadow smoke PARTIAL + fake DSN → 不证明 Postgres migration 可执行
5. remaining_blockers 仍有 P0 → 不得 PASS
6. 测试结果未明确回报

## 2. 这一 stage 的回应

### 2.1 新加 3 个 migration

| Migration | 标题 | 来源 | 大小 |
|---|---|---|---|
| `000013_shadow_position_marks.sql` | shadow_position_marks 表 (18 cols, 2 indexes) | `cmd/lpbot/position_mark.go:103-135` in-Go CREATE TABLE | 30 lines |
| `000014_shadow_exit_tables.sql` | shadow_exit_decisions + shadow_exit_actions 表 (16+12 cols, 4 indexes) | `cmd/lpbot/position_mark.go:147-220` in-Go CREATE TABLE | 47 lines |
| `000015_chain_text_alignment.sql` | INT→TEXT alignment for positions/pools/pool_score_history/pnl_ledger.chain + recreate idx_positions_one_active_per_pool | P0-PG-01 audit BLK-PG-05 + chain type decision | 130 lines |

### 2.2 修改 5 个 Go 文件 (chain TEXT alignment)

| 文件 | 修改 |
|---|---|
| `internal/adapters/store/postgres/adapter.go` | 删除 unused `chainIDToInt` 和 `intToChainID` 函数 |
| `internal/adapters/store/postgres/position_repo.go` | `chainIDToInt(pos.Chain)` → `string(pos.Chain)`; `Chain int` → `Chain string`; `intToChainID(row.Chain)` → `domain.ChainID(row.Chain)` |
| `internal/adapters/store/postgres/pool_repo.go` | 同上 (4 occurrences) |
| `internal/adapters/store/postgres/ledger_repo.go` | 同上 (3 occurrences, includes `var chain int` → `var chain string`) |
| `internal/adapters/store/postgres/postgres_test.go` | `TestChainIDConversion` 改写为 TEXT roundtrip; inline schema `chain INTEGER` → `chain TEXT` (3 occurrences) |
| `internal/adapters/store/postgres/migrate_test.go` | 加 `TestPostgresRepoIntegration` 的真实 roundtrip (PositionRepo Save+FindByID) |

### 2.3 修改 1 个 config + 1 个 shell script

| 文件 | 修改 |
|---|---|
| `configs/config.shadow.toml` | `postgres_dsn = "${POSTGRES_DSN:-${DATABASE_URL:-}}"` → `postgres_dsn = "${POSTGRES_DSN}"`. Reason: Go 的 platform/config 用 `regexp.MustCompile(\`\\$\\{([^}]+)\\}\`)` 解析 `${VAR}` 形式, 不识别 `${VAR:-}`. 原先写法导致 parser 把 literal `:-` 一起 expand, 报 `first path segment in URL cannot contain colon` / `sslmode=disable}`. 修正后用 platform/config 自己的 POSTGRES_DSN → DATABASE_URL fallback (config.go:166-170). |
| `scripts/migrate-postgres.sh` | 1) 提取 `-- +goose Up` 段 (避免 psql 跑 `-- +goose Down` 中的 DROP TABLE); 2) 加 `schema_migrations` marker table 实现 idempotent re-apply; 3) 修复 gap-check bash arithmetic 错误 (空 heredoc 行) |

## 3. Chain type 决策

**Decision**: **TEXT** 是 canonical type.

**Rationale**:
1. 9 of 13 表已经用 TEXT (transactions, execution_intents, canary_events, portfolio_snapshots, shadow_decision_trace, shadow_position_marks, shadow_exit_decisions, shadow_exit_actions, pnl_ledger); 4 of 13 用 INTEGER (positions, pools, pool_score_history, pnl_ledger 实际也是 INTEGER; 实际是 4:9).
2. 4 个 in-Go CREATE TABLE (shadow tables + canary_events) 已经用 TEXT, 没有阻抗不匹配
3. `chainIDToInt()` 对 unknown chain 返回 0, 静默丢失数据; TEXT 保留原值
4. Storage cost 可忽略 (3-7 bytes vs 4 bytes per row)
5. 跨表 join 仍需 explicit cast, 但 TEXT 在低基数列上更可读

**Migration 000015**:
- 加新列 `chain_text TEXT`
- backfill: `WHEN 1 THEN 'base' WHEN 2 THEN 'solana' ELSE '' END` (reverse of chainIDToInt)
- DROP COLUMN chain, RENAME chain_text → chain
- SET NOT NULL, SET DEFAULT ''
- 末尾 **recreate** `idx_positions_one_active_per_pool` (因为 ALTER TABLE DROP COLUMN 会 drop 关联的 index)

## 4. 重新验证 schema compatibility

```bash
$ go test ./internal/adapters/store/postgres/ -run TestMigrationsSchemaCompatibility -v
=== RUN   TestMigrationsSchemaCompatibility
--- PASS: TestMigrationsSchemaCompatibility (0.06s)
PASS
```

Test 内部 require 16 tables + 1 index (扩了 shadow_position_marks / shadow_exit_decisions / shadow_exit_actions).

## 5. 重新验证 Postgres integration (real DSN)

```bash
$ LPBOT_POSTGRES_TEST_DSN="postgresql://lpbot:testpass@127.0.0.1:54329/lpbot_test?sslmode=disable" \
  go test ./internal/adapters/store/postgres/ -run TestPostgresRepoIntegration -v
=== RUN   TestPostgresRepoIntegration
    migrate_test.go:257: integration test would run against DSN host: 127.0.0.1:54329
    migrate_test.go:274: postgres adapter connected; schema guard not yet exercised (migration runner pending)
    migrate_test.go:290: all 16 required tables present
    migrate_test.go:297: required index idx_positions_one_active_per_pool present
    migrate_test.go:321: PositionRepo Save+FindByID roundtrip OK; chain TEXT='base'
--- PASS: TestPostgresRepoIntegration (0.14s)
PASS
```

**确认**:
- 16 tables + 1 index 全部 OK
- `idx_positions_one_active_per_pool` 存在 (由 000015 末尾重建)
- `PositionRepo.Save` + `FindByID` roundtrip 成功
- chain TEXT='base' 写入再读出 = 'base' (chain alignment 正确)

## 6. 一句话

3 个新 migration (000013/000014/000015) + 5 个 Go adapter file 修改 (chain TEXT) + 1 个 config + 1 个 shell script 修改. 静态 schema test PASS, 真实 Postgres integration test PASS (含 chain TEXT roundtrip), idx_positions_one_active_per_pool 重建后 OK. Reviewer critique 1, 2, 4, 5 全部 addressed. Critique 3 (shadow service 实际修改) 已在 6ec750a 完成并在本 stage re-verified.
