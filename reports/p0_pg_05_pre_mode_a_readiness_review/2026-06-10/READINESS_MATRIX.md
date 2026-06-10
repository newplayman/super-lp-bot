# READINESS_MATRIX — P0-PG-05

18 dimensions. Each is rated PASS / WARN / FAIL / NOT_APPLICABLE, with
the supporting report and file path, and the blocking level
(P0 = must fix before any Mode A discussion; P1 = should fix before
opening Mode A; P2 = acceptable to take into Mode A as a known
follow-up; none = informational).

| # | Dimension | Status | Supporting report | Supporting file | Blocking |
|---|---|---|---|---|---|
| 1 | Postgres schema/code compatibility | PASS | `reports/p0_postgres_shadow_audit/2026-06-09/`, `reports/p0_postgres_shadow_deployment_fix/20260608_181508/` | `migrations/postgres/*.sql` (15 files, including the 4 the audit said were missing: 000011_shadow_decision_trace, 000013_shadow_position_marks, 000014_shadow_exit_tables, 000015_chain_text_alignment); shadow tables `shadow_outcome_labels_repaired_v2` and others present | none |
| 2 | Go migration runner | PASS | `reports/p0_pg_02e_migration_runner_idempotency/20260609_060000/` | `internal/adapters/store/postgres/migrator/` (discover.go / migrator.go / embed.go / migrator_test.go); `cmd/lpbot-migrate-postgres/main.go` | none |
| 3 | Migration idempotency | PASS | `reports/p0_pg_02e_migration_runner_idempotency/20260609_060000/IDEMPOTENCY_TEST_RESULTS.txt`, `reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/LOCAL_SHADOW_SMOKE_RUN_LOG.txt` | `internal/adapters/store/postgres/migrator/migrator.go::Apply` (per-migration transaction, ON CONFLICT DO NOTHING, pre-flight checksum verification of all applied rows) | none |
| 4 | Migration source sync guard | PASS | `reports/p0_pg_02f_migration_entrypoint_cleanup/2026-06-09/MIGRATION_SYNC_CHECK_REPORT.md` | `scripts/check_postgres_migrations_sync.sh`, `make check-postgres-migrations-sync` (step in `ci.yml` + `migration-quality-gate.yml` + `shadow-smoke-gate.yml`) | none |
| 5 | Migration CI quality gate | PASS | `reports/p0_pg_02g_ci_migration_quality_gate/2026-06-09/` | `.github/workflows/migration-quality-gate.yml` (postgres:16-alpine service, plan / apply / status / re-apply loop, full test suite) | none |
| 6 | Fresh Postgres migration verification | PASS | `reports/p0_pg_03_fresh_shadow_smoke/2026-06-09/MIGRATION_FRESH_DB_REPORT.md`, `reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/LOCAL_VALIDATION_RESULTS.txt` | `make migrate-postgres-plan / apply / status` exit 0 against fresh DB on the test container | none |
| 7 | Shadow startup smoke | PASS | `reports/p0_pg_03_fresh_shadow_smoke/2026-06-09/SHADOW_SMOKE_SUMMARY.md` | `bin/lpbot-shadow` ran 5 min, banner + metrics server + clean SIGTERM shutdown | none |
| 8 | Hardened no-RPC shadow smoke | PASS | `reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/NO_RPC_SMOKE_MODE_REPORT.md`, `SCHEMA_GUARD_ASSERTION_REPORT.md` | `cmd/lpbot/main.go::isSmokeNoRPCEnabled` + `runShadowSchemaGuard`; `scripts/check_shadow_smoke_safety.sh` requires `smoke_no_rpc_mode=true`, `base_rpc_initialization=skipped`, `schema_guard=ok` | none |
| 9 | CI hardened shadow smoke workflow | PASS (file authored, not yet run on GitHub Actions) | `reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/CI_SHADOW_SMOKE_WORKFLOW_REPORT.md` | `.github/workflows/shadow-smoke-gate.yml`; `scripts/check_ci_shadow_smoke_workflow_safety.sh` exit 0 | P2 (CI first-run status) |
| 10 | Full repo `go test ./...` | PASS | every TEST_RESULTS.txt in the lineage | `go test -count=1 ./...` exit 0 in P0-PG-02G, P0-PG-03, P0-PG-03B, P0-PG-04 | none |
| 11 | Focused `make test-race` | PASS | every TEST_RESULTS.txt in the lineage | `go test -race -count=1 ./internal/adapters/store/postgres ./internal/adapters/rpc` exit 0 in every canonical stage | none |
| 12 | Build targets (shadow / dryrun / live / migrator) | PASS | every TEST_RESULTS.txt in the lineage | `make build-migrate-postgres`, `make build-shadow`, `make build-dryrun`, `make build-live` exit 0 in every canonical stage | none |
| 13 | Safety locks | PASS | every SAFETY_LOCKS_RECHECK.json in the lineage | every check `false` / `OK` / `LOCKED` across all stages; this stage's SAFETY_LOCKS_RECHECK.json (this directory) confirms the same | none |
| 14 | R1 pause / R2 locked | PASS | `reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/FINAL_PAUSE_VERDICT.json` (status PAUSED); `r1_pause_respected=true` + `r2_locked=true` in every SAFETY_LOCKS_RECHECK.json | `reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/FORBIDDEN_ACTIONS_LOCK.json` enumerates 27 forbidden actions, all still locked | none |
| 15 | No wallet / no signing / no broadcast | PASS | every SAFETY_LOCKS_RECHECK.json in the lineage | `wallet_or_tx_touched`, `signing_attempted`, `broadcast_attempted` all false across all stages | none |
| 16 | No live / no canary / no paper / no probe | PASS | every SAFETY_LOCKS_RECHECK.json in the lineage | `canary_started`, `live_started`, `paper_started` all false; dryrun / live / canary binaries all "built but not executed" in every stage | none |
| 17 | Remaining schema / chain-type warnings | WARN | `reports/p0_pg_03_fresh_shadow_smoke/2026-06-09/SHADOW_SMOKE_SUMMARY.md`, every SAFETY_LOCKS_RECHECK.json | `cmd/lpbot/position_mark.go:220`: `chain: converting driver.Value type string ("base") to a int: invalid syntax`. Pre-existing; tracked under audit P0-PG-02-C (chain type alignment). | P2 |
| 18 | CI first-run status | WARN (file authored, not yet run on GitHub Actions) | `reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/CI_SHADOW_SMOKE_WORKFLOW_REPORT.md` | `.github/workflows/shadow-smoke-gate.yml` will run on the next push touching its trigger paths, on `workflow_dispatch`, or on the daily cron at 37 6 * * *. Local re-run (180s) PASSED. | P2 |

## Summary

- PASS: 14
- WARN: 2 (#17 chain-type warning, #18 CI first-run pending)
- FAIL: 0
- NOT_APPLICABLE: 0

P0 blockers: **0**.
P1 blockers: **0**.
P2 blockers: 2 (#17, #18; both already explicitly tracked in the canonical SAFETY_LOCKS_RECHECK.json of every relevant stage).