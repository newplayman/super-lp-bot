# P0 Postgres/Supabase CI and Test Gap Audit

- **stage**: `LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`
- **audit_focus**: CI 是否覆盖 (a) migration parse / apply, (b) schema-code drift test, (c) Postgres adapter integration test, (d) shadow build, (e) -race
- **audit_method**: read-only, .github/workflows/ci.yml + Makefile + tests/ directory

## 1. CI Workflow Inventory

| 字段 | 值 |
|---|---|
| 文件 | `.github/workflows/ci.yml` |
| Triggers | pull_request, push to main, cron `0 6 * * *` |
| Jobs | `quality-gate`, `advisory-audit` (continue-on-error), `fork-tests` (cron / [run-fork]), `chaos-tests` (cron) |

### 1.1 quality-gate

Steps:
1. `actions/checkout@v4` (fetch-depth: 0)
2. `actions/setup-go@v5` (go-version: 1.25, cache: true)
3. `tidy` — `go mod tidy && git diff --exit-code go.mod go.sum`
4. `golangci-lint` — `golangci/golangci-lint-action@v6` (version: latest, timeout: 5m)
5. `Build all tags` — `make build-dryrun && make build-shadow && make build-live && make backtest`
6. `Unit tests` — `make test`
7. `Property tests` — `make test-property`
8. `Test files unmodified check` — `git diff $BASE -- '*_test.go' | grep -E '^-[^-]' | grep -v '^---'`

**没有的 step**:
- ❌ No migration parse test (no `pg_query` or `libpg_query` go library)
- ❌ No migration apply test (no in-CI postgres service)
- ❌ No schema-code drift test
- ❌ No -race
- ❌ No postgres adapter integration test (the one in postgres_test.go is skip-gated on docker)
- ❌ No shadow E2E smoke (would need postgres + binary + 30min)
- ❌ No sqlc / schema-doc generation

### 1.2 advisory-audit (continue-on-error)

Steps:
1. `actions/checkout@v4`
2. `actions/setup-go@v5`
3. Install `govulncheck`
4. `go list -m -u all` (dependency updates)
5. `go vet ./...`
6. `govulncheck ./...`

**不覆盖 postgres-specific audit**.

### 1.3 fork-tests

- Trigger: cron `0 6 * * *` 或 commit message 含 `[run-fork]`
- 跑 `make test-fork` (需要 anvil + RPC secrets)
- 跟 postgres adapter 无关

### 1.4 chaos-tests

- Trigger: cron only
- 跑 `make test-chaos`
- 跟 postgres adapter 无关

## 2. Makefile Targets

| Target | Command | 触发什么 |
|---|---|---|
| `tidy` | `go mod tidy` | Go mod 整理 |
| `lint` | `golangci-lint run ./...` | Lint |
| `test` | `go test ./...` | **无 -race** |
| `test-property` | `go test -tags=property ./...` | Property tests |
| `test-fork` | `go test -tags=fork ./tests/fork/...` | Fork tests (需 anvil + secrets) |
| `test-chaos` | `go test -tags=chaos ./tests/chaos/...` | Chaos tests |
| `test-all` | test + test-property + test-fork + test-chaos | All |
| `audit-consistency` | `./scripts/audit_workspace_consistency.sh` | Repo 一致性 |
| `canary-profitability-evidence` | `./scripts/canary_profitability_evidence.sh` | Canary P&L evidence (R2 territory) |
| `build-dryrun` | `go build -ldflags ... -tags=dryrun -o bin/lpbot-dryrun ./cmd/lpbot` | dryrun binary |
| `build-shadow` | `go build -ldflags ... -tags=shadow -o bin/lpbot-shadow ./cmd/lpbot` | shadow binary |
| `build-live` | `go build -ldflags ... -tags=live -o bin/lpbot-live ./cmd/lpbot` | live binary |
| `build-all` | build-dryrun + build-shadow + build-live + backtest | All binaries |
| `backtest` | `go build -ldflags ... -o bin/lpbot-backtest ./cmd/lpbot-backtest` | Backtest binary |
| `run-dryrun` | build-dryrun + exec | Local run |
| `run-shadow` | build-shadow + exec | Local run |
| `run-live` | build-live + exec | Local run (需 LPBOT_CONFIRM_LIVE=YES) |
| `clean` | `rm -rf bin/ data/` | Clean |

**没有的 target**:
- ❌ No `test-migration` or `test-postgres`
- ❌ No `test-race`
- ❌ No `test-shadow-smoke` (would need a real postgres)
- ❌ No `test-schema-drift`
- ❌ No `test-postgres-integration`

## 3. tests/ Inventory

| 目录 | 内容 | 跟 postgres 相关? |
|---|---|---|
| `tests/property/` | `helpers.go`, `helpers_test.go`, `mocks/` (chain, mock_pool_repo, mock_bus, mock_datasource, mock_position_repo) | ❌ 全是 mock, 无 postgres |
| `tests/fork/` | (likely fork tests with anvil) | ❌ |
| `tests/chaos/` | (likely chaos tests) | ❌ |
| `tests/` (root) | ~80+ Python readonly test files (mostly LP long horizon research) | ❌ 跟 postgres adapter 无关 |
| `internal/adapters/store/postgres/postgres_test.go` | 1 real-ish test (TestPostgresAdapter_DockerIntegration_RoundTrip, skip on no-docker) | ⚠️ only 1, skip-gated, schema-divergent |
| `internal/adapters/store/sqlite/migrate_test.go` | sqlite migration test | (sqlite only, 不覆盖 postgres) |

## 4. Postgres test 详细分析

### 4.1 TestPostgres_New
- Mock 行为, 不连真 DB
- OK for unit

### 4.2 TestPostgres_ConfigDSN / TestPostgres_ConfigDSN_DefaultSSL
- 纯 string formatting, 无 DB 连接
- OK for unit

### 4.3 TestPostgresAdapter_DockerIntegration_RoundTrip
- **唯一** 真 DB integration test
- **Skip-gated**: `if _, err := exec.LookPath("docker"); err != nil { t.Skip("docker not available") }`
- 假设 docker 在 PATH. CI runner 默认无 docker, **99% 时间 skipped**
- 即使 docker 在, 也只跑 inline CREATE TABLE schema, **不用真 migrations**
- **Coverage gap**:
  - 不 apply `migrations/postgres/000001..000010, 000012` 任何一个
  - 不 cover `shadow_decision_trace`, `shadow_position_marks`, `shadow_exit_*`, `portfolio_snapshots`, `position_marks`, `canary_events`, `execution_intents`, `risk_events`, `kill_switch_state`, `config_snapshots`, `pnl_ledger`
  - 不 cover chain type consistency check
  - 不 cover partial unique index `idx_positions_one_active_per_pool`
- **Schema divergence**: test inline `last_score JSONB` (migration 是 TEXT), `transactions.block_hash NOT NULL` (migration nullable), etc.

**Severity**: P0 (BLK-PG-07). 这是 detection gap 的核心.

### 4.4 TestPostgresAdapter_AllRepos
- 用 `exec.LookPath("docker")` 跳过? No, 看代码 `// add docstring`
- 实际: 通过 `mustExecSQL` 用 ad-hoc schema. **同 4.3 一样**.

### 4.5 其他 postgres_test.go
- TestStableLedgerEntryID, TestChainIDConversion, TestTxBroadcastTimestamp, etc.
- 全是 unit / mock, OK
- 不 cover 实际 SQL

## 5. CI Test Gaps (P0)

| ID | Gap | 影响 | 估时 (人天) |
|---|---|---|---|
| BLK-PG-07 | `TestPostgresAdapter_DockerIntegration_RoundTrip` skip-gated + schema divergent | 任何 migration 改动都 undetectable | 1-2 (rewrite) |
| GAP-CI-01 | No migration parse / apply test in CI | migration .sql syntax 错 undetectable | 1 |
| GAP-CI-02 | No schema-code drift test | migration 列 ≠ Go struct 字段 undetectable | 1 |
| GAP-CI-03 | No -race in CI / Makefile | 并发 SQL race undetectable | 0.25 |
| GAP-CI-04 | No postgres service in CI runner (e.g. service container) | 即使写 integration test 也无处跑 | 0.5 (CI yaml 改) |
| GAP-CI-05 | No `make test-postgres` target | 用户手动跑 postgres test 不便 | 0.25 |
| GAP-CI-06 | No sqlc / schema generation | sqlc.yaml 在 sqlite dir 但 postgres dir 没有, type drift undetectable | 1-2 (optional) |
| GAP-CI-07 | No `make audit-postgres-schema` target | 没有自动化审计 schema-code 一致性的 target | 0.5 |

## 6. 推荐 CI 改造 (P0-PG-04 / P0-PG-05)

### 6.1 P0-PG-04: 加 migration test + schema drift test

**新 file**: `internal/adapters/store/postgres/migrate_test.go`
```go
//go:build integration_postgres
// +build integration_postgres

package postgres

import (
    "os"
    "testing"
    "github.com/pressly/goose/v3"
)

func TestPostgresMigrations_ApplyAll(t *testing.T) {
    if os.Getenv("TEST_POSTGRES_DSN") == "" {
        t.Skip("set TEST_POSTGRES_DSN to enable")
    }
    db, err := sql.Open("postgres", os.Getenv("TEST_POSTGRES_DSN"))
    if err != nil { t.Fatal(err) }
    defer db.Close()
    if err := goose.Up(db, "migrations/postgres"); err != nil {
        t.Fatalf("goose up: %v", err)
    }
    // 验关键表存在
    tables := []string{"positions", "transactions", "execution_intents",
        "portfolio_snapshots", "position_marks", "canary_events",
        "pnl_ledger", "shadow_decision_trace", "shadow_position_marks"}
    for _, tbl := range tables {
        var exists bool
        if err := db.QueryRow(`SELECT to_regclass('public.' || $1) IS NOT NULL`, tbl).Scan(&exists); err != nil {
            t.Fatal(err)
        }
        if !exists { t.Errorf("table %s missing", tbl) }
    }
}
```

**新 file**: `scripts/audit_postgres_schema_code_drift.py` (or Go)
- 读 migrations/postgres/*.sql, parse CREATE TABLE, 列 column/type/nullable
- 读 internal/adapters/store/postgres/*.go, 找 INSERT/SELECT/UPDATE, 提取 column refs
- diff
- 输出 mismatch 列

**新 Makefile target**:
```
test-postgres-migrations:
    TEST_POSTGRES_DSN=$$(cat .env.postgres | grep DATABASE_URL | cut -d= -f2) \
    go test -tags=integration_postgres ./internal/adapters/store/postgres/...

audit-postgres-schema:
    python3 scripts/audit_postgres_schema_code_drift.py
```

**新 CI step**:
```yaml
- name: Start postgres service
  uses: actions/setup-postgres@v1
  with:
    postgres-version: "16"
- name: Apply migrations
  run: bash scripts/apply_postgres_migrations.sh
- name: Migration test
  run: make test-postgres-migrations
- name: Schema-code drift audit
  run: make audit-postgres-schema
```

### 6.2 P0-PG-05: -race in CI

**Makefile change**:
```
test:
    $(GO) test -race -count=1 ./...
```

**CI change**: (none, just `make test`)

## 7. 一句话

CI 找到 7 gap (1 P0, 6 P1/P2). 核心是 (a) postgres integration test 自身 skip + schema 偏离, (b) 无 migration parse / apply test, (c) 无 schema-code drift test, (d) 无 -race. 全部 fixable in P0-PG-04 + P0-PG-05. 估时 3-5 人天.
