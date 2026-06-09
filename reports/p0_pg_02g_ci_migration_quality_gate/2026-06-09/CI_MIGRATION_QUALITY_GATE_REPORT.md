# CI_MIGRATION_QUALITY_GATE_REPORT — P0-PG-02G

## Scope

P0-PG-02G takes the migration work shipped in P0-PG-02E (Go runner) and
P0-PG-02F (thin shell wrapper + sync guard script) and turns it into a
**durable CI quality gate** so that future PRs cannot regress:

- the dual SQL source drift between `migrations/postgres/` and
  `internal/adapters/store/postgres/migrator/sql/`,
- the migration apply / plan / status paths against a fresh Postgres,
- the postgres adapter unit tests,
- the migrator's idempotency on a second apply.

The changes in this stage are **CI infrastructure only**; no
application code is touched.

## Changes

### `Makefile` — `quality-gate` target (new)

```makefile
quality-gate: check-postgres-migrations-sync test
```

Aggregates the cheap, fast, network-free checks. Deliberately **excludes**:

- `test-property` (uses internal goroutine stress; can be flaky)
- `test-fork` / `test-chaos` (need secrets, schedule-only)
- `migrate-postgres apply / plan / status` (need a live Postgres; those
  live in the new `migration-quality-gate.yml` workflow)

Documented in a comment immediately above the target so future
contributors understand why these particular checks were bundled.

### `.github/workflows/ci.yml` — extended `quality-gate` job

Two new steps added between the existing `Build all tags` and `Unit
tests` steps:

1. `make build-migrate-postgres` — added to the `Build all tags` step.
2. `make check-postgres-migrations-sync` — new dedicated step that
   fails the build on dual-source drift. Runs on every PR, every push
   to main, and the daily cron.

Both run on the existing `ubuntu-latest` runner with `setup-go@v5` and
Go 1.25; no new infrastructure is required.

### `.github/workflows/migration-quality-gate.yml` — new workflow

A dedicated workflow for the database-bound migration checks. Triggers:

- `pull_request` that touches any of the migration corpus paths
  (`migrations/postgres/**`, `internal/adapters/store/postgres/migrator/**`,
  `cmd/lpbot-migrate-postgres/**`, `scripts/migrate-postgres.sh`,
  `scripts/check_postgres_migrations_sync.sh`, `Makefile`, the
  workflow file itself).
- `push` to `feat/supabase-postgres-deployment` or `main`.
- Daily cron (offset to `17 6 * * *`, distinct from the main CI cron at
  `0 6 * * *`).

Job layout:

- `runs-on: ubuntu-latest`
- `services.postgres: postgres:16-alpine` with default credentials
  (`POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`,
  `POSTGRES_DB=lpbot_test`) and a `pg_isready` healthcheck.
- `env.POSTGRES_DSN=postgres://postgres:postgres@localhost:5432/lpbot_test?sslmode=disable`
  (this is the **only** DSN the runner sees in CI).
- Steps in order:
  1. `actions/checkout@v4` (fetch-depth: 0, for the test-files guard)
  2. `actions/setup-go@v5` (Go 1.25, cache: true)
  3. `make build-migrate-postgres`
  4. `make check-postgres-migrations-sync`
  5. Explicit `pg_isready` wait (belt-and-suspenders)
  6. `make migrate-postgres-plan` (pre-apply, should be all pending)
  7. `make migrate-postgres` (apply all)
  8. `make migrate-postgres-plan` (post-apply, should be 0 pending)
  9. `make migrate-postgres-status`
  10. `make migrate-postgres` again (must be no-op, validates
      idempotency)
  11. `go test -count=1 -timeout 5m ./internal/adapters/store/postgres/...`
  12. `go test -count=1 -timeout 15m ./...`
  13. `*_test.go` unmodified guard (same as main ci.yml)

The workflow reads **no** secrets, **no** wallet / signer / keypair
material, and **no** paid RPC. The only DSN is the in-network
postgres service. Concurrency group is `migration-quality-gate-${{
github.ref }}` with `cancel-in-progress: true` so re-runs do not
pile up.

## What was NOT changed

- `migrations/postgres/*.sql` — untouched.
- `internal/adapters/store/postgres/migrator/sql/*.sql` — untouched.
- The Go runner and the CLI — untouched.
- The existing `scripts/migrate-postgres.sh` thin wrapper — untouched.
- The existing `scripts/check_postgres_migrations_sync.sh` — untouched.
- The R1 pre-existing modification to
  `tests/test_lp_long_horizon_partial_12h_request_v1.py` — preserved.
- `make test-all` — NOT modified; the new `quality-gate` is a separate
  target. `test-all` continues to be the kitchen-sink run for
  power users; `quality-gate` is what the canonical CI path uses.

## Trade-offs and follow-ups

- The dedicated workflow uses `paths:` triggers to avoid running
  expensive migration verification on PRs that do not touch the
  migration corpus. The main `ci.yml` quality-gate still gets the
  cheap sync check on every PR via the `Build all tags` and
  `Migration sync check` steps.
- Concurrency cancellation is on; this is safe because the workflow
  is idempotent and the postgres service is per-run.
- The test-files guard in `migration-quality-gate.yml` reuses the
  same `git diff` pattern as the main `ci.yml` for consistency.
- `make quality-gate` is intentionally not added to the main
  `ci.yml` job: the main job already runs `make test` and the new
  `make check-postgres-migrations-sync` step, so adding the aggregate
  would just duplicate work. The new target exists for human use and
  for any future job that wants the fast pre-merge subset.
