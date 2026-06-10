# P2_RISK_ACCEPTANCE_MATRIX — P0-PG-06

This file is a single-purpose extract of section 3 of
`MODE_A_DISCUSSION_DRAFT.md`. The matrix enumerates each P2 blocker
carried forward from the P0-PG-05 readiness review and recommends
whether each should be accepted into any future Mode A discussion
stage. It exists as a standalone file so ChatGPT reviewers can read
the matrix without having to also parse the discussion narrative.

## Sources

- `reports/p0_pg_05_pre_mode_a_readiness_review/2026-06-10/BLOCKER_TRIAGE.md`
- `reports/p0_pg_05_pre_mode_a_readiness_review/2026-06-10/READINESS_MATRIX.md`
- `reports/p0_pg_05_pre_mode_a_readiness_review/2026-06-10/SAFETY_LOCKS_SUMMARY.md`
- `reports/p0_postgres_shadow_audit/2026-06-09/FINAL_AUDIT_VERDICT.json`

## Matrix

| # | P2 item | Recommend accept into Mode A discussion? | Accept into A1 (shadow soak)? | Accept into A2 (shadow + public RPC)? | Accept into A3 (dryrun replay)? |
|---|---|---|---|---|---|
| 1 | Pre-existing chain-type WARN from `cmd/lpbot/position_mark.go:220` (audit P0-PG-02-C) | YES (log noise only; contained to shadow strategy tick) | YES | YES | N/A (dryrun replay does not enter the strategy loop) |
| 2 | CI workflow `shadow-smoke-gate.yml` first-run pending | YES, sequenced | YES (CI gate must be green before A1 opens) | YES | YES |
| 3 | Dual SQL source on disk (`migrations/postgres/` + `migrator/sql/`) | YES (guarded by sync check) | YES | YES | YES |
| 4 | Live-mode vs shadow-mode schema guards still split | YES (shared `loadLiveSchemaState` helper) | YES | YES | YES |
| 5 | Public RPC health-probe fallback in canonical (non-no-RPC) shadow mode | YES, A2 only | NO (A1 uses no-RPC mode) | YES | N/A (dryrun mode does not open RPC adapters) |
| 6 | Smoke safety check is static string-grep | YES (covers the contract) | YES | YES | YES (A3 schema-guard variant) |
| 7 | Pre-existing R1 modified file preserved in working tree | YES (unchanged) | YES | YES | YES |
| 8 | CI test race target is narrow (focused) | YES (canonical decision) | YES | YES | YES |

## Cross-cuts

- **A1 (shadow soak, 60–120 min, no-RPC mode)**: items 1, 2, 3, 4, 6, 7, 8 are all acceptable; item 5 is N/A because A1 uses no-RPC mode.
- **A2 (shadow + public RPC, 30–60 min)**: items 1, 2, 3, 4, 5, 6, 7, 8 are all acceptable; the difference from A1 is that item 5 is now active and the smoke safety check must additionally verify the public-RPC outbound is read-only.
- **A3 (dryrun replay, 5–15 min, no chain)**: items 2, 3, 4, 6, 7, 8 are acceptable; items 1 and 5 are N/A because dryrun does not enter the strategy loop and does not open RPC adapters.

## Items that would change the verdict to NOT_READY_FIX_P0_FIRST

None of the eight P2 items above would individually block the
`READY_TO_TRIGGER_CI_FIRST_RUN_THEN_DISCUSS_MODE_A` verdict that
P0-PG-05 produced. If any of them were re-classified as P1 or P0,
the verdict would need to be re-derived:

- Re-classify item 1 (chain-type WARN) as P1 → does not by itself
  change the verdict (it's still noise) but ChatGPT would have to
  decide whether to require the fix in the same plan.
- Re-classify item 2 (CI first-run pending) as P0 → would force
  NOT_READY_FIX_P0_FIRST until the CI run completes green.
- Re-classify item 5 (public RPC fallback) as P1 → would force
  NOT_READY_FIX_P0_FIRST or READY_AFTER_P1_FIXES for A2 specifically;
  A1 and A3 remain acceptable.

None of these re-classifications have been requested by ChatGPT in
the P0-PG-05 acceptance message; this stage preserves the P2
classification as recorded.

## Items that the next plan stage must explicitly address

A future `LP_BOT_ENGINEERING_MODE_A*_PLAN_V1` stage must:

- Pick exactly one of A1 / A2 / A3.
- Carry the relevant subset of the matrix above into its own
  `P2_RISK_ACCEPTANCE_MATRIX.md`.
- State explicitly which items it accepts vs defers to a later
  stage.

No Mode A execution can begin without that plan stage landing
first.