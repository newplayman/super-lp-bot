# P0 Postgres/Supabase Fix Plan — P0-PG-02

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_DRIFT_FIX_V1` (recommended next stage)
- **triggered_by**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1` (this audit, status=WARN, ready_for_p0_pg_02_fix=true)
- **purpose**: 修 P0-PG-01 audit 找到的 8 P0 + 2 P1 blockers
- **scope**: 仅修本 audit 列出的 10 blockers. **不**进入 R2 / canary / live, **不**启动 shadow smoke (那是 P0-PG-03)

## 0. 一句话

本 plan 拆 P0-PG-02 为 5 个 sub-task (A B C D E), 全部 read-then-write-only-if-needed, 全部在 fresh dev DB 上 verify (不用 prod). 完成 P0-PG-02 后, P0-PG-03 (smoke) 才能 start.

## 1. Sub-task 列表 + 估时

| Sub-task | 标题 | 估时 (人天) | 估时 累计 |
|---|---|---|---|
| P0-PG-02-A | Add 3 missing-table migrations + 000011 placeholder fix | 1-2 | 1-2 |
| P0-PG-02-B | Consolidate 2 in-Go CREATE TABLE statements into migrations | 0.5 | 1.5-2.5 |
| P0-PG-02-C | Chain type alignment (decide INT vs TEXT) | 1 | 2.5-3.5 |
| P0-PG-02-D | `lpbot-shadow.service` add `EnvironmentFile=.env.postgres` + DSN fallback in config | 0.25 | 2.75-3.75 |
| P0-PG-02-E | Go migration runner + embed.FS (or goose) + checksum + ordering + 000004 idempotency | 2-3 | 4.75-6.75 |
| P0-PG-04 (后续) | CI: migration test + schema drift test + postgres service | 1-2 | 5.75-8.75 |
| P0-PG-05 (后续) | CI: -race | 0.25 | 6-9 |

**总估时**: 6-9 人天 (1 engineer full-time, 1.5-2 周)

## 2. P0-PG-02-A: Add 3 missing-table migrations + 000011 placeholder

### 2.1 Investigate 000011 gap (BLK-PG-04)

```bash
git log --all --diff-filter=D -- migrations/postgres/000011*.sql
git log --all --follow -- migrations/postgres/000012*.sql
```

确认 000011 是否被 deleted. 如果是, 重建 (内容 = shadow_decision_trace schema per `cmd/lpbot/decision_trace.go:55-95`). 如果 git history 没记录, 占位 000011 写 `-- 000011 reserved; see 000013_shadow_decision_trace.sql` (重新编号).

### 2.2 新 migration files

**`migrations/postgres/000011_shadow_decision_trace.sql`** (or 重新编号):
```sql
-- +goose Up
-- +goose StatementBegin
CREATE TABLE IF NOT EXISTS shadow_decision_trace (
    id BIGSERIAL PRIMARY KEY,
    tick_time BIGINT NOT NULL,
    trace_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    pool_key TEXT NOT NULL,
    chain TEXT NOT NULL,
    protocol TEXT NOT NULL,
    score_total DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    selected_rank INTEGER,
    selection_reason TEXT NOT NULL DEFAULT '',
    intent_open BOOLEAN NOT NULL DEFAULT FALSE,
    intent_reason TEXT NOT NULL DEFAULT '',
    chain_stage TEXT NOT NULL DEFAULT '',
    chain_reason TEXT NOT NULL DEFAULT '',
    pipeline_stage TEXT NOT NULL DEFAULT '',
    pipeline_ok BOOLEAN NOT NULL DEFAULT FALSE,
    pipeline_reason TEXT NOT NULL DEFAULT '',
    final_action TEXT NOT NULL DEFAULT 'skip',
    position_id TEXT,
    tx_hash TEXT,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_created_at
    ON shadow_decision_trace(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_tick_time
    ON shadow_decision_trace(tick_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_decision_trace_pool_id
    ON shadow_decision_trace(pool_id);
-- +goose StatementEnd
-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_decision_trace;
-- +goose StatementEnd
```

**`migrations/postgres/000013_shadow_position_marks.sql`** (after 000012):
```sql
-- +goose Up
-- +goose StatementBegin
CREATE TABLE IF NOT EXISTS shadow_position_marks (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    status TEXT NOT NULL,
    amount_usd TEXT NOT NULL DEFAULT '0',
    position_value_usd TEXT NOT NULL DEFAULT '0',
    fee_collected_usd TEXT NOT NULL DEFAULT '0',
    fee_uncollected_usd TEXT NOT NULL DEFAULT '0',
    gas_usd TEXT NOT NULL DEFAULT '0',
    il_usd TEXT NOT NULL DEFAULT '0',
    lvr_usd TEXT NOT NULL DEFAULT '0',
    net_pnl_usd TEXT NOT NULL DEFAULT '0',
    source TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    mark_time BIGINT NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_position_time
    ON shadow_position_marks(position_id, mark_time DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_position_marks_mark_time
    ON shadow_position_marks(mark_time DESC);
-- +goose StatementEnd
-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_position_marks;
-- +goose StatementEnd
```

**`migrations/postgres/000014_shadow_exit_tables.sql`**:
```sql
-- +goose Up
-- +goose StatementBegin
CREATE TABLE IF NOT EXISTS shadow_exit_decisions (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    -- ... 跟 cmd/lpbot/position_mark.go:147-180 schema 一致
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_exit_decisions_position
    ON shadow_exit_decisions(position_id, created_at DESC);

CREATE TABLE IF NOT EXISTS shadow_exit_actions (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    action TEXT NOT NULL,
    -- ... 跟 cmd/lpbot/position_mark.go:185-220 schema 一致
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_exit_actions_position
    ON shadow_exit_actions(position_id, created_at DESC);
-- +goose StatementEnd
-- +goose Down
-- +goose StatementBegin
DROP TABLE IF EXISTS shadow_exit_decisions;
DROP TABLE IF EXISTS shadow_exit_actions;
-- +goose StatementEnd
```

**acceptance**:
- `ls migrations/postgres/` 编号 000001-000014 连续 (无 gap)
- `psql -f migrations/postgres/000011..000014.sql` apply OK
- `cmd/lpbot/main.go:821` live schema guard pass

## 3. P0-PG-02-B: Consolidate in-Go CREATE TABLE

修 `cmd/lpbot/decision_trace.go:55-95`:
- 删 inline `CREATE TABLE IF NOT EXISTS shadow_decision_trace` + 3 indexes + 2 ALTER
- 改为: `_, err := provider.DB().ExecContext(ctx, "SELECT 1 FROM shadow_decision_trace LIMIT 1")` (verify exists, fail if not)
- 如果 table 不存在 → 抛错 "shadow_decision_trace missing; apply migrations/postgres/000011_*.sql"

修 `cmd/lpbot/position_mark.go:103-220`:
- 同上, 4 个 inline CREATE TABLE (shadow_position_marks, shadow_exit_decisions, shadow_exit_actions) 全部删
- 改为 verify-exists-or-fail pattern

**alternative**: 保留 in-Go CREATE 但加 idempotency check + log "table already exists in migration, ignoring in-Go CREATE".

**acceptance**:
- `cmd/lpbot/decision_trace.go` 不含 `CREATE TABLE IF NOT EXISTS shadow_decision_trace` 字串
- `cmd/lpbot/position_mark.go` 不含 `CREATE TABLE IF NOT EXISTS shadow_position_marks` 字串
- apply migrations + 启动 lpbot-shadow, 仍 OK

## 4. P0-PG-02-C: Chain type alignment

**decision needed**: INT vs TEXT for cross-table chain?

**推荐 INT** (理由):
- 已有 `chainIDToInt` helper
- 跨表 join 自然 (PK 是 pool_id+chain+protocol, INT 比 string 快)
- 更省 storage

**实施**:
1. 写 `migrations/postgres/000015_chain_int_alignment.sql`:
   ```sql
   -- +goose Up
   -- +goose StatementBegin
   -- 1. Add new column chain_int to transactions (nullable)
   ALTER TABLE transactions ADD COLUMN IF NOT EXISTS chain_int INTEGER;
   -- 2. Backfill: 'base' → 1, 'solana' → 2, others → 0
   UPDATE transactions SET chain_int = CASE chain
       WHEN 'base' THEN 1 WHEN 'solana' THEN 2 ELSE 0 END
   WHERE chain_int IS NULL;
   -- 3. Drop old, rename new
   ALTER TABLE transactions DROP COLUMN chain;
   ALTER TABLE transactions RENAME COLUMN chain_int TO chain;
   -- 4. Add NOT NULL constraint
   ALTER TABLE transactions ALTER COLUMN chain SET NOT NULL;
   ALTER TABLE transactions ALTER COLUMN chain SET DEFAULT 0;
   -- Similar for execution_intents, canary_events, shadow_decision_trace, shadow_position_marks
   -- +goose StatementEnd
   -- +goose Down: NOT REVERSIBLE (data conversion)
   ```
2. 修 `internal/adapters/store/postgres/tx_repo.go:35` 改 `chainIDToInt(tx.Chain)`
3. 修 `internal/adapters/store/postgres/execution_intent_repo.go:42` 改 `chainIDToInt(intent.Chain)`
4. 修 `cmd/lpbot/canary_state.go:166` chain value
5. 修 `cmd/lpbot/decision_trace.go:115` chain value
6. 修 `cmd/lpbot/position_mark.go:162` chain value
7. sqlite side: 同步改? (跨 store type 一致性)

**acceptance**:
- 所有表 `chain` 列类型统一 (INT)
- `tx.Chain` 在 tx_repo.go/execution_intent_repo.go 用 `chainIDToInt`
- 跨表 join 不需 cast

## 5. P0-PG-02-D: lpbot-shadow.service + DSN fallback

### 5.1 Edit `deploy/systemd/lpbot-shadow.service`

加:
```
[Service]
EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.postgres
EnvironmentFile=/opt/lpbot/lp-bot-v3/.env.redis
```

(before `ExecStartPre` line)

### 5.2 Edit `configs/config.shadow.toml`

改 line 26:
```toml
postgres_dsn = "${POSTGRES_DSN:-${DATABASE_URL:-}}"
```

(Go template-style fallback: POSTGRES_DSN > DATABASE_URL > empty)

### 5.3 Document in `docs/runbooks/vps-shadow-deployment.md`

加 step:
```bash
# Verify lpbot-shadow.service loads .env.postgres
sudo systemctl show lpbot-shadow -p EnvironmentFiles
# Should show: /opt/lpbot/lp-bot-v3/.env.postgres
```

### 5.4 Optional: New `scripts/check-postgres-migrations.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
source .env.postgres
psql "$DATABASE_URL" -c "SELECT to_regclass('public.shadow_decision_trace') IS NOT NULL" -t
# exit 0 if all required tables exist
```

**acceptance**:
- `sudo systemctl restart lpbot-shadow` 后, DSN 在 journalctl 不为空
- lpbot-shadow 启动 fail-clear (有明确 log)
- live schema guard pass (如果 migrations 完整)

## 6. P0-PG-02-E: Go migration runner + embed.FS

### 6.1 Decision: goose (推荐) or 自写

**方案 A: goose** (推荐):
- 加 `github.com/pressly/goose/v3` 到 go.mod
- 写 `internal/adapters/store/postgres/migrate.go`:
  ```go
  package postgres
  
  import (
      "database/sql"
      "embed"
      "github.com/pressly/goose/v3"
  )
  
  //go:embed migrations/*.sql
  var migrationsFS embed.FS
  
  func ApplyMigrations(db *sql.DB) error {
      goose.SetBaseFS(migrationsFS)
      if err := goose.SetDialect("postgres"); err != nil {
          return err
      }
      return goose.Up(db, "migrations")
  }
  
  func DownMigrations(db *sql.DB) error {
      goose.SetBaseFS(migrationsFS)
      if err := goose.SetDialect("postgres"); err != nil {
          return err
      }
      return goose.Down(db, "migrations")
  }
  ```
- 注意: embed.FS 在 internal/adapters/store/postgres/migrations/ 目录, 需要 symlink 或复制 migrations/postgres/*.sql. 或者用 `go:embed ../../../migrations/postgres/*.sql` (相对路径, 复杂).

**方案 B: 自写** (轻量):
- 写自己的 embed.FS + lexical sort + record `_migrations` table
- 不引外部依赖
- 估时 1-2 人天

**方案 C: 不修** (lowest):
- 保持 raw psql script
- 但加 (a) `ls migrations/postgres/*.sql | sort` 编号 gap check in apply_postgres_migrations.sh
- (b) `psql -c "CREATE TABLE IF NOT EXISTS _migrations(version BIGINT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"` + 记录已 apply 的 file

**推荐**: 方案 A (goose), 估时 1-2 人天 (含学习曲线).

### 6.2 000004 idempotency fix (BLK-PG-09)

加 flag column:
```sql
-- +goose Up
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS created_at_normalized BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE transactions SET created_at_normalized = TRUE
    WHERE created_at > 0 AND created_at > 2000000000
      AND created_at_normalized = FALSE;

-- 000004 改为:
UPDATE transactions
SET
    created_at = CASE WHEN created_at > 0 AND created_at < 2000000000 THEN created_at * 1000 ELSE created_at END,
    updated_at = CASE WHEN updated_at > 0 AND updated_at < 2000000000 THEN updated_at * 1000 ELSE updated_at END,
    broadcast_at = CASE WHEN broadcast_at > 0 AND broadcast_at < 2000000000 THEN broadcast_at * 1000 ELSE broadcast_at END,
    block_number = CASE WHEN block_number > 1000000000 THEN NULL ELSE block_number END
WHERE created_at_normalized = FALSE;
```

## 7. 验证步骤 (P0-PG-02 完成后)

```bash
# 1. Compile 干净
make lint
make build-all

# 2. Unit test 干净
make test

# 3. Set up fresh dev postgres (用 docker, 一次性)
docker run -d --rm -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=lpbot_dev -p 54322:5432 postgres:16-alpine

# 4. Apply migrations (新 goose 跑)
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/lpbot_dev?sslmode=disable"
go run ./cmd/lpbot-migrate  # (新 cmd, 调 postgres.ApplyMigrations)

# 5. Verify all 14 tables exist
psql $DATABASE_URL -c "\dt"

# 6. Start lpbot-shadow (用本地 binary, 不 systemd)
./bin/lpbot-shadow --config=configs/config.shadow.toml &
sleep 5
# check journal / log

# 7. Run integration test
TEST_POSTGRES_DSN=$DATABASE_URL go test -tags=integration_postgres ./internal/adapters/store/postgres/...

# 8. Cleanup
docker rm -f $(docker ps -q)
```

## 8. 严禁 (P0-PG-02 期间)

- ❌ 不进入 R1 / R2 / canary / live / paper / probe
- ❌ 不发 tx / mint / add liquidity
- ❌ 不连 wallet
- ❌ 不接 paid RPC
- ❌ 不写真实 secret
- ❌ 不 merge main / dev
- ❌ 不修改 R1 reports / data dirs
- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不使用 pkill -f
- ❌ 不连线上 prod DB
- ❌ 不跑 lpbot-shadow 长跑 (本 plan 是 dev DB 上 quick smoke, 后续 P0-PG-03 才长跑)

## 9. 一句话

P0-PG-02 拆 5 sub-tasks (A 1-2d + B 0.5d + C 1d + D 0.25d + E 2-3d), 估时 4.75-6.75 人天. 全部 fixable, 全部 verifiable in dev DB. 完成后 P0-PG-03 (smoke) 才能 start.
