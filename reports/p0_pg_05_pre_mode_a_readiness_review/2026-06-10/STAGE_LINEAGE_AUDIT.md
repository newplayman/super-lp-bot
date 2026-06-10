# STAGE_LINEAGE_AUDIT — P0-PG-05

Pre-Mode-A readiness review. Aggregates every canonical report on this
branch (and a small number of related read-only artifacts) into one
auditable lineage.

## Canonical lineage (engineering path)

| # | Stage | Status | base_commit | final_commit | Pushed | Report dir | Role |
|---|---|---|---|---|---|---|---|
| 1 | P0-PG-01 audit (`LP_BOT_ENGINEERING_P0_POSTGRES_SHADOW_AUDIT_V1`) | WARN | `ed84970` (commit_before in audit) | not a stage — audit-only | n/a (audit, not a stage) | `reports/p0_postgres_shadow_audit/2026-06-09/` | Read-only audit. Identified 10 blockers (BLK-PG-01..10). Marked `ready_for_p0_pg_02_fix: true`. |
| 2 | P0-PG-02E migration runner idempotency (`LP_BOT_ENGINEERING_P0_PG_02E_MIGRATION_RUNNER_IDEMPOTENCY_V1`) | PASS | `a22eb86` | `bf6fd27` (commit SHA shortened) | yes (canonical) | `reports/p0_pg_02e_migration_runner_idempotency/20260609_060000/` | Added `internal/adapters/store/postgres/migrator/`, `cmd/lpbot-migrate-postgres/`, the thin shell wrapper. Resolved BLK-PG-04..08. |
| 3 | P0-PG-02 shadow deployment fix chain (`P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1` etc.) | WARN | not a single commit | not a single commit | yes (canonical) | `reports/p0_postgres_shadow_deployment_fix/20260608_181508/`, `.../repair_cleanup/20260608_210000/`, `.../review_repair/20260608_190000/` | Closed BLK-PG-01..03 (missing migrations) and BLK-PG-05..06 (shadow service + config). Resolved audit warnings to WARN, not PASS, because some RPC integration tests stayed partial. |
| 4 | P0-PG-02F migration entrypoint cleanup (`LP_BOT_ENGINEERING_P0_PG_02F_MIGRATION_ENTRYPOINT_CLEANUP_V1`) | WARN | `4796ac9` | `580432a` (commit SHA shortened) | yes (canonical) | `reports/p0_pg_02f_migration_entrypoint_cleanup/2026-06-09/` | Converted `scripts/migrate-postgres.sh` from 233-line awk/psql loop to 45-line `exec` wrapper; added `scripts/check_postgres_migrations_sync.sh` + Makefile target. WARN at the time because fresh-PG end-to-end was not re-run locally; that gap was closed in P0-PG-02G. |
| 5 | P0-PG-02G migration CI quality gate (`LP_BOT_ENGINEERING_P0_PG_02G_CI_MIGRATION_QUALITY_GATE_V1`) | PASS | `580432a` | `883251b` | yes (canonical) | `reports/p0_pg_02g_ci_migration_quality_gate/2026-06-09/` | Added `make quality-gate`; added `.github/workflows/migration-quality-gate.yml`; re-ran plan/apply/status/reapply end-to-end against the existing test fixture. Closed P0-PG-02F's WARN. |
| 6 | P1 test suite stabilization (`LP_BOT_ENGINEERING_P1_TEST_SUITE_STABILIZATION_V1`) | PASS | `4796ac9` (between P0-PG-02E and P0-PG-02F) | not single | yes (canonical) | `reports/p1_test_suite_stabilization/20260609_053000/` | Stabilized `internal/adapters/rpc/roundrobin.go` flakes; pre-existing flake unrelated to migration. |
| 7 | P0-PG-03 fresh shadow smoke (`LP_BOT_ENGINEERING_P0_PG_03_FRESH_SHADOW_SMOKE_V1`) | PASS | `883251b` | `1addd97` (implementation), `fe689c6` (report-fill), `672b514` (clarify) | yes (canonical) | `reports/p0_pg_03_fresh_shadow_smoke/2026-06-09/` | First end-to-end shadow smoke against a fresh DB; introduced `configs/config.shadow.smoke.example.toml`, `scripts/run_shadow_smoke.sh`, `scripts/check_shadow_smoke_safety.sh` (v1). |
| 8 | P0-PG-03B shadow smoke hardening (`LP_BOT_ENGINEERING_P0_PG_03B_SHADOW_SMOKE_HARDENING_V1`) | PASS | `672b514` | `b3d34bb` (implementation), `e760e7b` (report-fill), `280c605` (clarify) | yes (canonical) | `reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/` | Added `LPBOT_SMOKE_NO_RPC=1` smoke mode that suppresses hardcoded public-RPC fallback and QuickNode discovery; added `runShadowSchemaGuard` in `cmd/lpbot/main.go`; hardened the safety check to require `schema_guard=ok`, `smoke_no_rpc_mode=true`, `base_rpc_initialization=skipped`. |
| 9 | P0-PG-04 CI hardened shadow smoke (`LP_BOT_ENGINEERING_P0_PG_04_CI_HARDENED_SHADOW_SMOKE_V1`) | PASS | `e707152` | `4a6656c` (implementation), `3e6808f` (report-fill), `c041766` (clarify) | yes (canonical) | `reports/p0_pg_04_ci_hardened_shadow_smoke/2026-06-09/` | Added `.github/workflows/shadow-smoke-gate.yml` (postgres:16-alpine + redis:7-alpine services, no secrets, LPBOT_SMOKE_NO_RPC=1, 180s CI smoke window) and `scripts/check_ci_shadow_smoke_workflow_safety.sh` + `make check-ci-shadow-smoke-workflow`. |

## Related read-only artifacts (not engineering stages)

| Artifact | Status | Role |
|---|---|---|
| `reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/FINAL_PAUSE_VERDICT.json` | PAUSED | R1 pause decision; R1 still paused; R2 still LOCKED (actual_fee_data_available=false); forbidden_actions_still_zero=true. |
| `reports/lp_long_horizon_r1_pause_and_freeze/20260607_191500/FORBIDDEN_ACTIONS_LOCK.json` | LOCKED | 27 forbidden actions explicitly enumerated and locked during pause. |
| `reports/p0_postgres_shadow_audit/2026-06-09/FINAL_AUDIT_VERDICT.json` | WARN | 10 blockers (BLK-PG-01..10); ready_for_p0_pg_02_fix=true. Audit-only. |

## Superseded reports

- `reports/p0_pg_03_fresh_shadow_smoke/2026-06-09/` (P0-PG-03) is **superseded**
  for schema-guard semantics by
  `reports/p0_pg_03b_shadow_smoke_hardening/2026-06-09/` (P0-PG-03B). The
  P0-PG-03B shadow smoke added the `runShadowSchemaGuard` log line that
  P0-PG-03 claimed but did not actually emit; P0-PG-03's safety check
  could not verify schema-guard success and that was its open issue.
  Both reports remain canonical for the version of code they shipped
  — P0-PG-03 is the "fresh shadow smoke" milestone, P0-PG-03B is the
  "hardened shadow smoke" milestone that fixed its gap.
- The P0-PG-02F "WARN" verdict is **superseded** by P0-PG-02G's "PASS"
  for the migrate-plan/status end-to-end gate; the WARN was closed
  explicitly in 02G's `02F_HANDOFF_SUMMARY.md`.

## Non-canonical / out-of-scope

- `reports/FINAL_VERDICT.json` (top-level, generated by
  `scripts/aggregate-verdict`) — aggregate snapshot only; not a stage
  FINAL_VERDICT.
- `reports/lp_*` directories (40+ reports) — read-only LP research
  artifacts under freeze; the canonical R1 verdict is the only one
  referenced by this readiness review.
- `reports/fee_velocity_*`, `reports/fixed_horizon_*`, `reports/tier*`,
  `reports/pool_regime_*`, etc. — historical research / engineering
  reports from earlier waves; not in the P0-PG lineage.

## What was NOT done in any of the canonical stages

- No `make run-dryrun`, `make run-shadow`, or `make run-live` was ever
  invoked. The shadow binary was executed **only** inside the bounded
  smoke (P0-PG-03, P0-PG-03B, P0-PG-04). The dryrun and live binaries
  were built but never run.
- No `LPBOT_CONFIRM_LIVE=YES` was ever set. All safety checks confirm
  this (booleans false in every SAFETY_LOCKS_RECHECK.json).
- No wallet, signer, keypair, mnemonic, or seed was ever used or
  referenced in any of the canonical stages.
- No merge to main / dev. All commits live on
  `feat/supabase-postgres-deployment`.
- No R1 reports / data dirs were modified by any P0-PG-* stage.
- No long-horizon collector was restarted.