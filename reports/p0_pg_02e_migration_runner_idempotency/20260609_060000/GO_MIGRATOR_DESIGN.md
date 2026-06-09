# P0-PG-02E — Go Migrator Design

- **stage**: `LP_BOT_ENGINEERING_P0_PG_02E_MIGRATION_RUNNER_IDEMPOTENCY_V1`
- **run_id**: `20260609_060000`
- **base_commit**: `a22eb86`
- **branch**: `feat/supabase-postgres-deployment`

## 1. Design goals

| Goal | Achieved by |
|------|-------------|
| Replace ad-hoc shell script with a Go-based runner | `internal/adapters/store/postgres/migrator` package + `cmd/lpbot-migrate-postgres` CLI |
| Transaction-per-migration (fail closed) | `db.BeginTx` → `ExecContext(upSQL)` → `INSERT schema_migrations` → `Commit`. Error at any step → `Rollback` + stop. |
| Idempotency (re-run = no-op) | `schema_migrations` table tracks filenames. Already-applied = `Skipped` in `ApplyResult`. |
| Checksum tracking | SHA256 of file content recorded in `schema_migrations.checksum`. Re-running checks: if recorded != file, refuse to proceed. |
| Production-DSN safety | Refuse DSN containing "supabase.co", "rds.amazonaws.com", "prod", "production" unless `LPBOT_MIGRATE_ALLOW_LIVE=YES`. |
| No canary/live env autoload | Do NOT auto-load `.env.canary`, `.env.live`, or any canary/live env. Only `POSTGRES_DSN` or `DATABASE_URL` from explicit env. |
| Test coverage | 8 unit + 7 integration tests in `migrator_test.go`. |

## 2. Package layout

```
internal/adapters/store/postgres/migrator/
├── migrator.go          # Runner struct, Plan/Status/Apply methods
├── migrations.go        # //go:embed all:sql
├── sql/                 # 15 embedded .sql files
│   ├── 000001_init_schema.sql
│   ├── ...
│   └── 000015_chain_text_alignment.sql
└── migrator_test.go     # 15 tests

cmd/lpbot-migrate-postgres/
└── main.go              # CLI with plan/status/apply subcommands
```

## 3. Migrator API

```go
type Mode string
const (
    ModePlan   Mode = "plan"
    ModeStatus Mode = "status"
    ModeApply  Mode = "apply"
)

type Config struct {
    DSN           string
    MigrationsFS  fs.FS
    MigrationsDir string
    AllowLiveDSN  bool
}

type Runner struct { ... }

func NewRunner(ctx context.Context, cfg Config) (*Runner, error)
func (r *Runner) Close() error
func (r *Runner) Plan(ctx context.Context) (*PlanResult, error)
func (r *Runner) Status(ctx context.Context) (*StatusResult, error)
func (r *Runner) Apply(ctx context.Context) (*ApplyResult, error)
```

## 4. schema_migrations table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    checksum   TEXT NOT NULL DEFAULT '',
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

Three columns:
- `filename` (PK): the migration's `.sql` filename
- `checksum`: SHA256 of the file content. Empty string ('') is a legacy marker; the runner backfills on first apply.
- `applied_at`: timestamp (set to NOW() at insert time)

Legacy migration rows (created by the pre-Go shell runner) have no `checksum` column at all. The runner's `ensureChecksumColumn` adds the column with default `''` so the table is forward-compatible.

## 5. Transaction model

For each pending migration `f`:

```
BEGIN TRANSACTION
  -- Apply the Up section of f (DROP TABLE etc. stripped out)
  EXECUTE extractUpSection(f.content)
  -- Record in the same transaction (no partial-failure window)
  INSERT INTO schema_migrations(filename, checksum)
  VALUES (f.filename, f.checksum)
COMMIT
```

If any step fails, the transaction is rolled back; the `schema_migrations` row is NOT inserted; the runner stops. **No partial state is left in the DB**.

## 6. Checksum-mismatch protection

Before applying any new migration, the runner checks each `schema_migrations` row:

```
for each f in r.files:
    if applied[f.filename] exists AND applied[f.filename] != f.checksum:
        refuse to proceed (avoid replaying incompatible SQL on a partially-applied DB)
```

This is a **safety net**, not a normal-path operation. In normal operation, the file content of a migration never changes after it's been applied. If it does (e.g. a developer accidentally edits a committed file), the runner refuses to continue.

## 7. Production-DSN guard

The runner refuses DSNs containing:
- `supabase.co`
- `rds.amazonaws.com`
- `prod` (substring)
- `production` (substring)

unless `LPBOT_MIGRATE_ALLOW_LIVE=YES` env var is set, or `Config.AllowLiveDSN=true`.

The check is intentionally conservative (false positives are safer than false negatives).

## 8. Env-file autoload policy

The runner does **NOT** read any `.env` file. It only reads:
- `POSTGRES_DSN` (preferred)
- `DATABASE_URL` (fallback)

If both are empty, the runner exits 2 with a hint.

The runner **does not** auto-load:
- `.env.canary`
- `.env.live`
- Any other canary/live env file

This is enforced by the test `TestRunner_NoEnvCanaryOrLiveAutoLoad` which exercises a path where the runner would pick up a canary env if it auto-loaded, and verifies it doesn't.

## 9. CLI design

`cmd/lpbot-migrate-postgres`:

```
$ lpbot-migrate-postgres plan
{
  "files": [ ... 15 .sql filenames ... ],
  "to_apply": [ ... filenames not in schema_migrations ... ],
  "already_applied": [ ... filenames in schema_migrations ... ]
}

$ lpbot-migrate-postgres status
{
  "applied": [ { "filename": "...", "checksum": "..." } ... ],
  "missing": [ ... ]  // required tables/indexes NOT present
  "required": [ "positions", ..., "idx_positions_one_active_per_pool" ],
  "all_present": true|false
}
# Exit 0 if all_present, exit 4 if any missing

$ lpbot-migrate-postgres apply
{
  "applied": [ ... filenames newly applied ... ],
  "skipped": [ ... filenames already applied ... ],
  "failed_at": "",  // empty on success
  "failed_err": "",  // empty on success
  "was_partial": false
}
# Exit 0 on success, exit 5 on any failure
```

DSN resolution: `$POSTGRES_DSN` > `$DATABASE_URL`.

The CLI also rejects production DSNs unless `LPBOT_MIGRATE_ALLOW_LIVE=YES`. The CLI is the only place where env files are read — and the CLI doesn't read them, it only reads env vars.

## 10. Makefile integration

```makefile
build-migrate-postgres:
    $(GO) build -o bin/lpbot-migrate-postgres ./cmd/lpbot-migrate-postgres

migrate-postgres:
    ./bin/lpbot-migrate-postgres apply

migrate-postgres-plan:
    ./bin/lpbot-migrate-postgres plan

migrate-postgres-status:
    ./bin/lpbot-migrate-postgres status
```

The Makefile now invokes the Go binary. `scripts/migrate-postgres.sh` is retained as a legacy alias (the binary is the canonical entry point).

## 11. Test coverage (15 tests)

| Test | Layer | DSN required? | What it verifies |
|------|-------|---------------|------------------|
| TestExtractUpSection_StripsDownSection | unit | no | DROP TABLE from -- +goose Down section is NOT in the Up extraction |
| TestLooksLikeProductionDSN | unit | no | Production DSN heuristic catches 4 markers |
| TestDSNHost_StripsCredentials | unit | no | dsnHost returns only "host[:port]" — no creds in logs |
| TestRunner_AllowLiveDSN_PermitsProductionDSN | unit | no (closed port) | AllowLiveDSN bypasses production check |
| TestRunner_RejectsProductionDSN_WithoutAllowLiveDSN | unit | no (refused early) | Default refuses production DSNs |
| TestRunner_NoEnvCanaryOrLiveAutoLoad | unit | no (closed port) | DSN source is explicit Config.DSN only |
| TestRunner_ProductionDSNGate_RespectsEnvVar | unit | no (closed port) | LPBOT_MIGRATE_ALLOW_LIVE=YES bypasses check |
| TestMigrator_PlanListsAllMigrations | integration | yes | 15 files in embed.FS, plan output |
| TestMigrator_ApplyOnFreshDB | integration | yes | Apply 15 on DROP SCHEMA → 15 applied, all_present=true |
| TestMigrator_ReRunIsNoOp | integration | yes | Second Apply: 0 applied, 15 skipped |
| TestMigrator_ChecksumMismatchRefuses | integration | yes | Mutated file → second Apply refuses |
| TestMigrator_PerMigrationTransactionRollback | integration | yes | 2 migrations, 2nd fails mid-statement → 1st committed, 2nd rolled back |
| TestMigrator_StatusReturnsCorrectFields | integration | yes | Status: 15 applied with real checksums |
| TestMigrator_LegacyDB_BackfillOnFirstApply | integration | yes | checksum='' pre-populated → backfill on first Apply |
| TestMigrator_PostgresAdapterIntegrationStillPasses | integration | yes | Required tables + index = 17 (16 tables + 1 idx) |

## 12. 一句话

Go-based migration runner 实现为 internal/adapters/store/postgres/migrator (核心) + cmd/lpbot-migrate-postgres (CLI) + Makefile (wire-in). 15 migration 通过 embed.FS 进入 binary. schema_migrations 表记录 (filename, checksum, applied_at). 每 migration 独立 transaction + checksum 验证 + legacy backfill. Production-DSN guard 启用. .env.canary / .env.live 不自动加载. 15 unit + integration test 全部 PASS.
