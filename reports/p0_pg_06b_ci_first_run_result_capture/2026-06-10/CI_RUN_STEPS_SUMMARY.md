# CI_RUN_STEPS_SUMMARY — P0-PG-06B

## Why this file is mostly empty

This stage could not read the GitHub Actions run from this host
because `gh` is not authenticated and no `GH_TOKEN` / `GITHUB_TOKEN`
is present in the environment. The per-step results of the
`shadow-smoke-gate.yml` workflow run are therefore not available
to be recorded here.

## Expected workflow steps (per the workflow file)

For reference, this is the step sequence the workflow was
authored with in P0-PG-04 (`reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/CI_SHADOW_SMOKE_WORKFLOW_REPORT.md`):

| # | Step | Expected on green |
|---|---|---|
| 1 | `actions/checkout@v4` with fetch-depth: 0 | ok |
| 2 | `actions/setup-go@v5` (Go 1.25, cache: true) | ok |
| 3 | `Show Go version` (`go version`) | ok |
| 4 | `Build migrator binary` (`make build-migrate-postgres`) | ok |
| 5 | `Migration sync check` (`make check-postgres-migrations-sync`) | ok |
| 6 | `Wait for postgres service` (`pg_isready` loop, 30s max) | ok |
| 7 | `Wait for redis service` (`redis-cli ping` loop, 30s max) | ok |
| 8 | `Migration pre-plan` (`make migrate-postgres-plan`) | pending=15, applied=null |
| 9 | `Migration apply` (`make migrate-postgres`) | ran=15 |
| 10 | `Migration post-plan` (`make migrate-postgres-plan`) | pending=null, applied=15 |
| 11 | `Migration status` (`make migrate-postgres-status`) | all_present=true |
| 12 | `Migration reapply (idempotency check)` (`make migrate-postgres`) | ran=null, skipped=15 |
| 13 | `Build shadow binary` (`make build-shadow`) | ok |
| 14 | `Materialize smoke config from template` (`cp ...`) | ok |
| 15 | `Run hardened shadow smoke (180s CI window)` (`scripts/run_shadow_smoke.sh`) | exit 124 (timeout), normalized to 0 |
| 16 | `Smoke safety check` (`SMOKE_LOG_DIR=... bash scripts/check_shadow_smoke_safety.sh`) | ok |
| 17 | `Static workflow safety check` (`./scripts/check_ci_shadow_smoke_workflow_safety.sh`) | ok |
| 18 | `Test files unmodified check` (`git diff '*_test.go'`) | ok |

Each step that involves the shadow smoke also emits the
required positive evidence lines in stdout/stderr:

- `Running in shadow mode: simulating transactions without real execution.`
- `metrics server started`
- `schema_guard=ok backend=postgres checked_relations=9`
- `smoke_no_rpc_mode=true; base_rpc_initialization=skipped`
- `smoke_no_rpc_mode=true; solana_rpc_initialization=skipped`

The smoke safety check (`scripts/check_shadow_smoke_safety.sh`)
asserts that all five lines are present in the log and that no
forbidden tokens (`panic:`, `FATAL`, `sendTransaction`,
`LPBOT_CONFIRM_LIVE`, action verbs) appear. A green run requires
all five required evidence lines + zero forbidden tokens.

## What was observed in this stage

Nothing. The CI run that should have been triggered by the
P0-PG-06 commit (`ea3bf446cec178ce650f87cc68dd311f96e489f3`)
cannot be read from this host. No per-step result can be
recorded honestly.

## How to close this

See `P0_PG_06_WARN_CLOSURE.md` for the explicit closure path.

The short version: a reviewer with browser access or authenticated
`gh` reads the run and feeds the values back. This stage then
becomes PASS.