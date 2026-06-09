# CI_SHADOW_SMOKE_WORKFLOW_REPORT — P0-PG-04

## What was added

`.github/workflows/shadow-smoke-gate.yml` — a dedicated GitHub
Actions workflow that runs the same hardened shadow smoke flow the
local P0-PG-03B work proved, but inside CI against a fresh
`postgres:16-alpine` + `redis:7-alpine` service pair. Designed to
be the durable gate before Mode A / Mode B opens.

## Trigger surface

- `workflow_dispatch` (manual run)
- daily cron at `37 6 * * *` (offset from the main CI cron's
  `0 6 * * *`)
- push to `feat/supabase-postgres-deployment` that touches any of:
  `cmd/lpbot/**`, `internal/**`,
  `configs/config.shadow.smoke.example.toml`,
  `scripts/run_shadow_smoke.sh`,
  `scripts/check_shadow_smoke_safety.sh`,
  `scripts/check_postgres_migrations_sync.sh`,
  `scripts/check_ci_shadow_smoke_workflow_safety.sh`,
  `migrations/postgres/**`,
  `internal/adapters/store/postgres/migrator/**`,
  `.github/workflows/shadow-smoke-gate.yml`,
  `Makefile`

`concurrency.cancel-in-progress: true` so re-runs don't pile up.

## Services

- `postgres:16-alpine` with `POSTGRES_USER=postgres`,
  `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=lpbot_smoke_ci`,
  port 5432, plus a `pg_isready` healthcheck.
- `redis:7-alpine` on port 6379, plus a `redis-cli ping` healthcheck.

Both are sibling containers; the runner connects via
`localhost:5432` / `localhost:6379`. No external infra.

## Env (no secrets)

- `POSTGRES_DSN=postgres://postgres:postgres@localhost:5432/lpbot_smoke_ci?sslmode=disable`
- `REDIS_URL=redis://localhost:6379/0`
- `LPBOT_SMOKE_NO_RPC=1`

The workflow reads **no** GitHub Actions secrets, **no**
`BASE_RPC_PRIMARY`, `SOL_RPC_PRIMARY`, `KMS`, `WALLET`,
`PRIVATE_KEY`, `MNEMONIC`, `SEED`, `LPBOT_CONFIRM_LIVE`,
`LPBOT_CANARY`, `LPBOT_LIVE`, `CANARY_DSN`, or `LIVE_DSN`.
This is enforced both by absence in the workflow file and by the
static `scripts/check_ci_shadow_smoke_workflow_safety.sh` check.

## Steps

1. `actions/checkout@v4` (fetch-depth: 0, for the test-files guard)
2. `actions/setup-go@v5` (Go 1.25, cache: true)
3. `go version`
4. `make build-migrate-postgres`
5. `make check-postgres-migrations-sync`
6. explicit `pg_isready` wait (belt-and-suspenders)
7. explicit `redis-cli ping` wait
8. `make migrate-postgres-plan` (pre-apply; expect 15 pending)
9. `make migrate-postgres`
10. `make migrate-postgres-plan` (post-apply; expect 0 pending)
11. `make migrate-postgres-status` (expect all_present=true)
12. `make migrate-postgres` (reapply; expect no-op)
13. `make build-shadow`
14. `cp configs/config.shadow.smoke.example.toml configs/config.shadow.smoke.toml`
15. `scripts/run_shadow_smoke.sh --config ... --duration 180 --log-dir reports/ci_shadow_smoke`
16. `SMOKE_LOG_DIR=... bash scripts/check_shadow_smoke_safety.sh` (required positive evidence + forbidden patterns)
17. `./scripts/check_ci_shadow_smoke_workflow_safety.sh` (the workflow does not reference any forbidden token and does reference all required tokens)
18. `*_test.go` unmodified guard

The180s CI window is shorter than the canonical local300s window to
keep the GitHub Actions run within the default 6-hour cap. The
local P0-PG-03B smoke remains the authoritative 300s bound.

## Static workflow safety check (scripts/check_ci_shadow_smoke_workflow_safety.sh)

Strips YAML comments before scanning, so a token documented in a
comment is not flagged, but a token appearing as an actual YAML
value will fail the check.

Forbidden tokens (must be absent from the workflow body):

| token | why |
|---|---|
| `secrets.` | Workflow should not reference any GitHub secret |
| `LPBOT_CONFIRM_LIVE=YES` | Live-mode gate must not be set |
| `PRIVATE_KEY` | Wallet / signer key would never belong here |
| `MNEMONIC` | Same |
| `SEED` | Same |
| `KMS` | No KMS endpoint |
| `CANARY_DSN` | No canary DSN |
| `LIVE_DSN` | No live DSN |
| `BASE_RPC_PRIMARY` | Smoke has no-RPC mode; no base RPC |
| `SOL_RPC_PRIMARY` | Same for solana |
| `run-live` | Do not invoke the live binary |
| `bin/lpbot-live` | Same |
| `run-dryrun` | Do not invoke the dryrun binary |
| `bin/lpbot-dryrun` | Same |

Required tokens (must be present):

| token | why |
|---|---|
| `postgres:16-alpine` | Postgres service |
| `redis:7-alpine` | Redis service |
| `LPBOT_SMOKE_NO_RPC` | No-RPC mode wired into the env |
| `make build-migrate-postgres` | Build migrator |
| `make migrate-postgres` | Apply migrations |
| `make migrate-postgres-status` | Status check |
| `make build-shadow` | Build shadow binary |
| `run_shadow_smoke.sh` | Run the smoke |
| `check_shadow_smoke_safety.sh` | Run the safety check |

## What the workflow does NOT do

- Does not read any GitHub Actions secret.
- Does not run `make run-dryrun`, `make run-shadow` (only
  `scripts/run_shadow_smoke.sh`, which is bounded and self-contained).
- Does not run `make run-live`, the live binary, or any
  canary / paper / probe path.
- Does not modify the codebase (no checkout-and-write paths).
- Does not write to any GitHub Actions cache key that crosses
  workflow runs.

## Empirical evidence (local re-run, 180s)

- `make check-ci-shadow-smoke-workflow` exit 0
  (this Makefile target now invokes the same check).
- `./scripts/check_ci_shadow_smoke_workflow_safety.sh` exit 0
  (output captured in `CI_WORKFLOW_SAFETY_CHECK.txt`).
- Local 180s shadow smoke run after applying migrations: exit 0.
- `scripts/check_shadow_smoke_safety.sh` against the local log: exit 0.
- Required evidence present in the log:
  `smoke_no_rpc_mode=true; base_rpc_initialization=skipped`
  `smoke_no_rpc_mode=true; solana_rpc_initialization=skipped`
  `schema_guard=ok backend=postgres checked_relations=9`
- Zero chain endpoint references in the log.

## CI execution caveat

This workflow has been authored but not yet run on GitHub Actions
(this host has no `act` runner). It will execute on the next push
to `feat/supabase-postgres-deployment` that touches one of the
trigger paths, or via `workflow_dispatch`, or on the daily cron.
That caveat is recorded in `remaining_blockers`.