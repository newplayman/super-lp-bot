# P0 Postgres/Supabase Schema-Code Drift Audit

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`
- **audit_focus**: 对比 `migrations/postgres/*.sql` vs Go code 实际使用的表/列/类型/索引, 列出 drift
- **audit_method**: read-only, 12 migration files + 8 postgres adapter .go files + cmd/lpbot/*.go grep

## 1. Migrations Inventory (postgres)

| # | 文件 | 字节 | 创建 / 修改的表 / 列 |
|---|---|---|---|
| 000001 | init_schema.sql | 3674 | transactions, positions, pools, pool_score_history, pnl_ledger, risk_events, kill_switch_state, config_snapshots |
| 000002 | canary_state.sql | 1476 | canary_events (id, chain, command, ..., required_usdc_raw, ..., created_at, updated_at) + 3 indexes |
| 000003 | pool_runtime_columns.sql | 526 | ALTER pools ADD liquidity/tick/tvl_usd/vol_24h/fee_apr_24h |
| 000004 | transactions_timestamp_cleanup.sql | 852 | UPDATE transactions (timestamp normalization) — **non-idempotent** |
| 000005 | positions_runtime_metadata.sql | 428 | ALTER positions ADD protocol/open_tx_hash/metadata(JSONB) |
| 000006 | active_position_uniqueness.sql | 363 | CREATE UNIQUE INDEX idx_positions_one_active_per_pool (partial) |
| 000007 | execution_intents.sql | 1037 | execution_intents + 3 indexes |
| 000008 | portfolio_snapshots.sql | 1007 | portfolio_snapshots + 1 index |
| 000009 | pnl_v1_and_position_marks.sql | 2793 | ALTER pnl_ledger, ALTER portfolio_snapshots, CREATE position_marks + 2 indexes |
| 000010 | shadow_outcome_labels.sql | 1359 | shadow_outcome_labels + 3 indexes |
| **GAP** | (no 000011) | — | 跳号, **migration 编号 gap 异常** |
| 000012 | shadow_outcome_repaired_v2.sql | 1959 | shadow_outcome_labels_repaired_v2 + 4 indexes |

**Note**: sqlite 仅有 7 migrations (000001-000007), 没有 shadow_outcome_labels / shadow_outcome_repaired_v2 / canary_events 的对应 sqlite migration. Postgres 独有.

## 2. Postgres Adapter Go Code (per-file SQL usage)

| Go 文件 | 行数 | 主要 SQL 操作 | 引用的表 / 列 |
|---|---|---|---|
| adapter.go | ~330 | 连接池, repo 路由 | (无直接 SQL) |
| position_repo.go | ~270 | Save / FindByID / FindByPoolAndStatus / FindByChainAndStatus / UpdateStatus / Snapshot | positions (id, token_id, pool_id, chain, protocol, status, tier, tick_lower, tick_upper, amount_usd, open_tx_hash, metadata, opened_at, closed_at) — chain 用 chainIDToInt → int |
| pool_repo.go | ~370 | UpsertPool (transactional) / GetPool / ListPools / GetScoreHistory / UpsertAuditVerdict | pools, pool_score_history — chain 用 chainIDToInt → int; liquidity/tick/tvl_usd/vol_24h/fee_apr_24h 都读写 |
| tx_repo.go | ~360 | UpsertTx / GetTxByHash / ListTxsByStatus / UpdateTxStatus / ListPendingTxs / ListStuckTxs / IncrementRFBAttempts / GetRFBAttempts | transactions — chain **passed as `string(chain)`** (TEXT) |
| ledger_repo.go | ~190 | Append / ByPosition / ByPositionAndKind / AggregateByKind / LatestBlock | pnl_ledger — chain 用 chainIDToInt → int |
| risk_repo.go | ~190 | AppendRiskEvent / ListRiskEvents / GetKillState / UpsertKillState | risk_events, kill_switch_state |
| execution_intent_repo.go | ~150 | Reserve / FindByID / FindByIdempotencyKey / FindByTxHash / Update | execution_intents — chain **passed as `string(intent.Chain)`** (TEXT) |

## 3. In-Go CREATE TABLE / Migrations 之外的 Schema 定义

这些是 **在 Go runtime 创建的表**, 不在 migrations:

| Go 文件 | 行 | 表 | schema 内容 | 触发点 |
|---|---|---|---|---|
| `cmd/lpbot/decision_trace.go` | 55-95 | `shadow_decision_trace` | id BIGSERIAL PK + tick_time/trace_id/pool_id/pool_key/chain/protocol/score_total/score_json/selected/selected_rank/selection_reason/intent_open/intent_reason/chain_stage/chain_reason/pipeline_stage/pipeline_ok/pipeline_reason/final_action/position_id/tx_hash/created_at + 3 indexes + 2 ALTER ADD COLUMN | `ensureShadowDecisionTraceTable` from main.go |
| `cmd/lpbot/position_mark.go` | 103-135 | `shadow_position_marks` | id BIGSERIAL PK + position_id/pool_id/chain/status/amount_usd/position_value_usd/.../mark_time/created_at + 2 indexes + 2 ALTER ADD COLUMN | `ensureShadowPositionMarksTable` from main.go |
| `cmd/lpbot/position_mark.go` | 147-180 | `shadow_exit_decisions` | id BIGSERIAL PK + position_id/pool_id/decision/... | (类似 ensure*) |
| `cmd/lpbot/position_mark.go` | 185-220 | `shadow_exit_actions` | id BIGSERIAL PK + position_id/pool_id/action/... | (类似 ensure*) |

**这是 schema-vs-code drift**: schema 在 Go code 里, 不在 migration 里. 即使 migration 完整 apply, 这些表的**结构**由代码决定, migration 不 source-of-truth. 这违背了 "schema 在 migration, code 适配 schema" 的原则.

## 4. Schema 引用 vs Migration 存在性

按 user spec 重点 audit 的 8 个关键对象:

| 对象 | Migration 中存在? | Code 中引用? | 一致? |
|---|---|---|---|
| positions | ✅ 000001 (+ 000003 ALTER, 000005 ALTER, 000006 unique index) | ✅ position_repo.go | ✅ |
| pools | ✅ 000001 (+ 000003 ALTER runtime cols) | ✅ pool_repo.go | ✅ |
| execution_intents | ✅ 000007 | ✅ execution_intent_repo.go | ✅ |
| portfolio_snapshots | ✅ 000008 (+ 000009 ALTER stuck counts) | ✅ cmd/lpbot/main.go:817 + portfolio_snapshot.go | ✅ |
| position_marks | ✅ 000009 | ✅ cmd/lpbot/main.go:818 + pnl_v1.go | ✅ |
| canary_events | ✅ 000002 | ✅ cmd/lpbot/canary_state.go:166 | ✅ |
| shadow_decision_trace | ❌ **无 migration** (在 cmd/lpbot/decision_trace.go:55 in-Go CREATE) | ✅ cmd/lpbot/main.go:821, canary_state.go:303, decision_trace.go | ❌ **drift** |
| shadow_position_marks | ❌ **无 migration** (在 cmd/lpbot/position_mark.go:103 in-Go CREATE) | ✅ cmd/lpbot/dashboard.go:1266/1888/2101, canary_reconcile_mint.go:259, canary_state.go:430 | ❌ **drift** |
| shadow_outcome_labels | ✅ 000010 | ✅ cmd/lpbot/main.go + pnl_v1.go + shadow_outcomes.go | ✅ |
| shadow_outcome_labels_repaired_v2 | ✅ 000012 | ❌ **未被任何 Go code 引用** (只在 test shadow_outcomes_test.go:76 CREATE 时作为参考) | ⚠️ 死表 |
| shadow_exit_decisions | ❌ **无 migration** (in position_mark.go:147 in-Go CREATE) | ✅ position_mark.go | ❌ **drift** |
| shadow_exit_actions | ❌ **无 migration** (in position_mark.go:185 in-Go CREATE) | ✅ position_mark.go | ❌ **drift** |
| idx_positions_one_active_per_pool | ✅ 000006 (partial index WHERE status IN ('intended',...)) | ✅ (main.go:821 includes in live schema guard) | ✅ |
| config_snapshots | ✅ 000001 | ❌ (postgres adapter.go:108 `ConfigSnap() = nil`) | ⚠️ dead table |

## 5. Schema-Code Drift Findings (per table / column / index)

### 5.1 BLK-PG-01 (P0) — shadow_decision_trace 缺 migration

- **表**: `shadow_decision_trace`
- **Migration**: ❌ 任何 postgres migration 都没 CREATE
- **Code 写入**: `cmd/lpbot/decision_trace.go:55-95` (in-Go CREATE TABLE IF NOT EXISTS) + `decision_trace.go:115` (INSERT)
- **Code 读取**: `cmd/lpbot/main.go:821` (live schema guard require) + `canary_state.go:303` (SELECT)
- **缺失字段**: 无 (代码 in-Go CREATE 完整)
- **类型**: code 定义 DOUBLE PRECISION, BOOLEAN, INTEGER, TEXT, BIGINT
- **Nullability**: code 设 NOT NULL DEFAULT
- **Index**: code 建 3 个 indexes
- **影响**: 任何 fresh VPS 部署只 apply migrations, 不启动 lpbot-shadow 进程, 不会触发 in-Go CREATE. 之后 lpbot-shadow 启动, main.go:821 live schema guard 会 fail with `relation shadow_decision_trace does not exist`. **Blocker**.
- **Fix (P0-PG-02-A)**: 写 `migrations/postgres/000011_shadow_decision_trace.sql` (并填补 000011 编号 gap), 同步 column / index / ALTER.

### 5.2 BLK-PG-02 (P0) — shadow_position_marks 缺 migration

- **表**: `shadow_position_marks`
- **Migration**: ❌
- **Code 写入**: `cmd/lpbot/position_mark.go:103-135` (in-Go CREATE) + `position_mark.go:162` (INSERT) + `canary_reconcile_mint.go:259` (DELETE)
- **Code 读取**: `cmd/lpbot/dashboard.go:1266,1888,2101` (SELECT) + `canary_state.go:430` (SELECT)
- **影响**: dashboard SELECT 会 fail. canary_reconcile_mint.go DELETE 会 fail.
- **Fix (P0-PG-02-A)**: 写 `migrations/postgres/000013_shadow_position_marks.sql` (after 000011/000012).

### 5.3 BLK-PG-03 (P0) — shadow_exit_decisions + shadow_exit_actions 缺 migration

- **表**: `shadow_exit_decisions`, `shadow_exit_actions`
- **Migration**: ❌
- **Code 写入**: `cmd/lpbot/position_mark.go:147, 185` (in-Go CREATE) + INSERT
- **影响**: 任何写/读这两表的代码会 fail.
- **Fix (P0-PG-02-A)**: 写 `migrations/postgres/000014_shadow_exit_tables.sql`.

### 5.4 BLK-PG-04 (P0) — Migration file numbering gap (000010 → 000012, no 000011)

- **现象**: `migrations/postgres/` 编号 000001-000010, 跳到 000012. 缺 000011.
- **可能性**:
  1. 一个 000011 migration 曾经存在但被 git rebase 删了
  2. 编号错误: 000012 应是 000011, 后续还有 000012
  3. 000011 还没 commit (在工作区)
- **风险**: 任何在 000010 → 000012 之间意图的 schema 改动, 已 **silently lost**. Goose / apply_postgres_migrations.sh lexical order 不会重建丢失的表.
- **Fix (P0-PG-02-A)**: 
  - `git log --diff-filter=D -- migrations/postgres/000011*.sql` 查 000011 是否被删
  - 如果是, 重建 (含 5.1 的 shadow_decision_trace 内容)
  - 任何 000011 占位 commit 也行 (e.g. `-- 000011 reserved for shadow_decision_trace; see 000011_shadow_decision_trace.sql`)

### 5.5 BLK-PG-05 (P0) — Chain column type inconsistency (TEXT vs INTEGER)

| 表 | chain 类型 (in migration) | code 写入方式 |
|---|---|---|
| positions | INTEGER | `chainIDToInt(pos.Chain)` → int |
| pools | INTEGER | `chainIDToInt(pool.Pool.Chain)` → int |
| pnl_ledger | INTEGER | `chainIDToInt(entry.BlockRef.Chain)` → int |
| transactions | TEXT | `tx.Chain` (passed as string) |
| execution_intents | TEXT | `string(intent.Chain)` |
| canary_events | TEXT (DEFAULT '') | (很少 chain 引用) |
| shadow_decision_trace (in-Go) | TEXT | `string(record.Chain)` |
| shadow_position_marks (in-Go) | TEXT | (类似) |

- **drift**: 同 field (chain) 跨 8 个表用 2 种类型 (INT 在 3 表, TEXT 在 5 表)
- **影响**:
  - 跨表 JOIN 必须显式 cast: `JOIN positions p ON p.chain = (CASE WHEN t.chain = 'base' THEN 1 WHEN t.chain = 'solana' THEN 2 END)`
  - Reporting SQL (e.g. `SELECT chain, count(*) FROM positions UNION SELECT chain, count(*) FROM transactions`) 会产生 type mismatch error
  - 任何 future 数据迁移 (postgres → postgres, postgres → sqlite) 因 type 不一致需要 schema 重建
- **设计选择**:
  - **方案 A**: 全部改 INT. 加 migration `000015_chain_int_alignment.sql`, 修 `transactions.chain` 和 `execution_intents.chain` 为 INT. 改 tx_repo.go 和 execution_intent_repo.go 用 chainIDToInt.
  - **方案 B**: 全部改 TEXT. 加 migration `000015_chain_text_alignment.sql`, 修 `positions.chain` 等为 TEXT. 改 position_repo.go / pool_repo.go / ledger_repo.go 用 string(chain).
  - **方案 C**: 接受现状, 加 `CHECK (chain IN ('1','2','3'))` + `CREATE CAST` 让跨表 JOIN 工作. 但仍 design 不洁.
- **Fix (P0-PG-02-C)**: 选方案 A 或 B, 用户决定. 建议 **方案 A** (INT, 因为 `chainIDToInt` 是已有 helper, 改 transactions/execution_intents 即可).

### 5.6 BLK-PG-06 (P0) — lpbot-shadow.service 缺 EnvironmentFile

详见 `03_DEPLOYMENT_RUNNABILITY_AUDIT.md` §3.

### 5.7 BLK-PG-07 (P0) — Postgres integration test 自身 schema 偏离

- **文件**: `internal/adapters/store/postgres/postgres_test.go:303 TestPostgresAdapter_DockerIntegration_RoundTrip`
- **gating**: `if _, err := exec.LookPath("docker"); err != nil { t.Skip("docker not available") }`
- **schema divergence**:
  - test inline `CREATE TABLE positions` 用 `last_score JSONB` → **migration 000001 用 TEXT** (实际不存在 last_score 在 000001; pool.Repo 写 `last_score TEXT` via `scoreJSON`)
  - test inline `CREATE TABLE transactions` 用 `block_hash NOT NULL`, `gas_limit BIGINT` 等 → **migration 用 `block_hash TEXT` (nullable), `gas_limit TEXT` (nullable)**
  - test 不 CREATE: `shadow_decision_trace`, `shadow_position_marks`, `shadow_exit_*`, `portfolio_snapshots`, `position_marks`, `canary_events`, `execution_intents`, `risk_events`, `kill_switch_state`, `config_snapshots`, `pnl_ledger` 等
- **影响**: 跑了 docker test 也只覆盖 4 表 (positions/transactions/pools/pool_score_history), 不能 detect schema drift.
- **Fix (P0-PG-04)**: 重写 test 用 `apply_postgres_migrations.sh` 真 apply 12 个 migration, 跑 real schema. 加 `t.Skip` 改 `t.Skip("set TEST_POSTGRES_DSN=... and migrations to test")`. 或用 `dockertest` Go library.

### 5.8 BLK-PG-08 (P0) — No Go migration runner / no embed / no goose

- **现状**:
  - `internal/adapters/store/postgres/` 8 个 .go 文件, **无** `migrate.go`
  - `internal/adapters/store/sqlite/` 有 `migrate.go` + `migrate_test.go` (有 Go-based migration runner)
  - `go.mod` 无 `github.com/pressly/goose` 或 `github.com/golang-migrate/migrate`
  - `scripts/apply_postgres_migrations.sh` 用 raw `psql -f migrations/postgres/*.sql`, **无 version tracking, 无 checksum, 无 rollback, 无 atomicity**
- **影响**:
  - 失败时部分 apply 难以恢复 (000004 non-idempotent, 部分 apply 之后不能重试)
  - lpbot-shadow 启动时不能 verify migration version
  - 不能 in-test apply migration
  - 任何加 migration 必须 push .sql + 同步 apply_postgres_migrations.sh 改一下 (没自动化)
- **Fix (P0-PG-02-E)**:
  - **方案 A (推荐)**: 加 `github.com/pressly/goose/v3` 到 go.mod, 写 `internal/adapters/store/postgres/migrate.go` 用 `embed.FS` 嵌入 migrations, 提供 `Apply(dsn, dir)` API. apply_postgres_migrations.sh 改为调 `bin/lpbot-migrate` (新 cmd).
  - **方案 B (轻量)**: 写自己的 `migrate.go` + `embed.FS` + 按 lexical 顺序 apply + 记录 `_migrations` 表. 不引外部依赖.
  - **方案 C (不修)**: 保持现状, 但加 2 个 sanity check: (a) `ls migrations/postgres/*.sql | sort` 编号无 gap, (b) 每个 .sql header 有 `-- +goose Up/Down` annotation.

### 5.9 BLK-PG-09 (P1) — 000004 non-idempotent

- **文件**: `migrations/postgres/000004_transactions_timestamp_cleanup.sql:11-25`
- **SQL**: `UPDATE transactions SET created_at = CASE WHEN created_at > 0 AND created_at < 2000000000 THEN created_at * 1000 ELSE created_at END`
- **现状**: 第一次 run 安全 (created_at < 2000000000 → × 1000). 第二次 run no-op (因为 × 1000 后 > 2000000000). 但如果**partial apply** 之后部分 row 已被 × 1000, 部分还没, 重试时部分行 no-op 部分行 × 1000, 导致 inconsistent state.
- **Fix (P0-PG-02-E)**: 加一个 flag column `created_at_normalized BOOLEAN DEFAULT FALSE` + 000004 改为 `WHERE NOT created_at_normalized` + 末尾 `UPDATE ... SET created_at_normalized = TRUE`.

### 5.10 BLK-PG-10 (P1) — No -race

- **现状**: Makefile `test` = `go test ./...` (无 -race). CI workflow `make test` (无 -race).
- **影响**: shadow 现在写 postgres, 并发 UpsertTx / UpdateStatus / ListStuckTxs 不能 detect race.
- **Fix (P0-PG-05)**: Makefile `test` 改 `go test -race -count=1 ./...`. CI 加 `make test-race` step.

## 6. Type Mismatch / Nullability / Index 详细对比

按 user spec 重点 audit 的字段: 仅列与 code 不一致 / 缺失 / 类型错:

| table.column | migration | code read | code write | issue |
|---|---|---|---|---|
| positions.protocol | TEXT (000005 ADD COLUMN, nullable) | COALESCE(protocol, '') | pos.Protocol | nullable 但 code 用 COALESCE 兼容, OK |
| positions.open_tx_hash | TEXT (000005 ADD COLUMN, nullable) | COALESCE(open_tx_hash, '') | pos.OpenTxHash | nullable 但 code 用 COALESCE 兼容, OK |
| positions.metadata | JSONB (000005) | COALESCE(metadata::text, '{}') | defaultPositionMetadataJSON | OK |
| pools.liquidity | TEXT NOT NULL DEFAULT '0' (000003) | sql.NullString, parsed via MustDecimal | pool.Pool.Liquidity.String() | OK |
| pools.tick | BIGINT NOT NULL DEFAULT 0 (000003) | sql.NullInt64 | pool.Pool.Tick | OK |
| pools.tvl_usd | TEXT (000003) | sql.NullString, parsed | pool.Pool.TVLUSD.String() | OK |
| pools.vol_24h | TEXT (000003) | sql.NullString, parsed | pool.Pool.Vol24h.String() | OK |
| pools.fee_apr_24h | TEXT (000003) | sql.NullString, parsed | pool.Pool.FeeAPR24h.String() | OK |
| pnl_ledger.pool_id | TEXT NOT NULL DEFAULT '' (000009) | (read in aggregate) | (write in Append via 000009 column) | OK |
| pnl_ledger.source | TEXT NOT NULL DEFAULT '' (000009) | (similar) | (similar) | OK |
| pnl_ledger.position_value_usd | TEXT NOT NULL DEFAULT '0' (000009) | (read) | (write) | OK |
| pnl_ledger.fee_collected_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.fee_uncollected_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.gas_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.il_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.lvr_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.net_pnl_usd | TEXT (000009) | (read) | (write) | OK |
| pnl_ledger.trace_id | TEXT (000009) | (read) | (write) | OK |
| position_marks.position_id | TEXT NOT NULL (000009) | (read in cmd/lpbot) | (write in cmd/lpbot) | OK |
| position_marks.pool_id | TEXT NOT NULL (000009) | (read) | (write) | OK |
| position_marks.chain | TEXT NOT NULL (000009) | (read) | (write) | OK |
| position_marks.token_id | TEXT (000009, nullable) | (read) | (write) | OK |
| position_marks.status | TEXT NOT NULL (000009) | (read) | (write) | OK |
| position_marks.amount_usd | TEXT NOT NULL DEFAULT '0' (000009) | (read) | (write) | OK |
| position_marks.position_value_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.fee_collected_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.fee_uncollected_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.gas_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.il_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.lvr_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.net_pnl_usd | TEXT (000009) | (read) | (write) | OK |
| position_marks.source | TEXT (000009) | (read) | (write) | OK |
| position_marks.metadata_json | JSONB (000009) | (read) | (write) | OK |
| position_marks.mark_time | BIGINT NOT NULL (000009) | (read) | (write) | OK |
| position_marks.created_at | BIGINT NOT NULL (000009) | (read) | (write) | OK |
| execution_intents.risk_snapshot_json | JSONB (000007) | COALESCE(::text, '{}') | `$N::jsonb` cast | OK |
| execution_intents.sizing_snapshot_json | JSONB (000007) | similar | similar | OK |
| portfolio_snapshots.balances_json | JSONB (000008) | (read) | (write) | OK |
| portfolio_snapshots.positions_json | JSONB (000008) | (read) | (write) | OK |
| shadow_outcome_labels.score_total | DOUBLE PRECISION (000010) | (read) | (write) | OK |
| shadow_outcome_labels_repaired_v2.score_total | DOUBLE PRECISION (000012) | (没 code 引用) | (没 code 引用) | **死表** |

**总结**: 大多数列 schema/code 一致. **drift 集中在**:
1. 3 个 shadow_* 表 (BLK-PG-01..03) 不在 migration
2. 1 个 migration 编号 gap (BLK-PG-04)
3. chain 类型跨表不一致 (BLK-PG-05)
4. systemd EnvironmentFile 缺失 (BLK-PG-06, 在 03)
5. test schema 偏离 (BLK-PG-07)
6. 无 Go migration runner (BLK-PG-08)
7. 000004 non-idempotent (BLK-PG-09, P1)
8. 无 -race (BLK-PG-10, P1)

## 7. 跨表 join / 报表查询的隐含风险

未来任何 cross-table SQL (e.g. `SELECT p.pool_id, t.tx_hash FROM positions p JOIN transactions t ON t.chain = p.chain ...`) 都会因 chain type mismatch 失败. Reporting SQL in `cmd/lpbot/pnl_v1.go`, `cmd/lpbot/portfolio_snapshot.go` 必须先做 cast 或用 string concat workaround.

## 8. 修复优先级 (per drift)

| Priority | drift | 估时 (人天) |
|---|---|---|
| P0 | BLK-PG-01 (missing shadow_decision_trace migration) | 0.5 |
| P0 | BLK-PG-02 (missing shadow_position_marks migration) | 0.5 |
| P0 | BLK-PG-03 (missing shadow_exit_* migrations) | 0.5 |
| P0 | BLK-PG-04 (migration 000011 gap investigate) | 0.25 |
| P0 | BLK-PG-05 (chain type align) | 1 |
| P0 | BLK-PG-06 (systemd EnvironmentFile) | 0.25 |
| P0 | BLK-PG-07 (postgres integration test real-schema) | 1-2 |
| P0 | BLK-PG-08 (Go migration runner) | 2-3 |
| P1 | BLK-PG-09 (000004 idempotency) | 0.25 |
| P1 | BLK-PG-10 (-race in CI) | 0.25 |

详见 `05_FIX_PLAN_P0_PG_02.md` §3.

## 9. 一句话

8 P0 + 2 P1 drift 找到, 集中在 (a) 3 missing shadow_* table migrations, (b) 1 numbering gap, (c) chain type inconsistency, (d) deployment, (e) test divergence, (f) no Go migration runner, (g) 000004 non-idempotent, (h) no -race. 全部 fixable in P0-PG-02. ready_for_p0_pg_02_fix=true.
