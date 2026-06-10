# BLOCKER_TRIAGE — P0-PG-05

Aggregates every `remaining_blockers` entry from the canonical
P0-PG-* SAFETY_LOCKS_RECHECK.json files (P0-PG-02F, P0-PG-02G,
P0-PG-03, P0-PG-03B, P0-PG-04) and the P0-PG-01 audit top-10
blockers, dedupes, classifies by severity, and lists explicit
risk-acceptance conditions for any P1 that this stage decides to
carry into Mode A.

## Deduplicated blockers (after canonical stages)

### P0 — must fix before any Mode A discussion

None.

The P0-PG-01 audit identified 10 blockers (BLK-PG-01..10). All of
them are closed in the canonical P0-PG-02E + P0-PG-02 shadow
deployment fix lineage, except the chain-type alignment (which is
classified P2 below per the audit's own recommendation; the audit
marked `ready_for_p0_pg_02_fix=true` and the lineage closed the
P0 items).

### P1 — should fix before opening Mode A; risk-acceptance only with explicit log

None.

### P2 — acceptable to carry into Mode A as a known follow-up

1. **Pre-existing chain-type WARN from `cmd/lpbot/position_mark.go:220`**
   (audit P0-PG-02-C). Every canonical stage from P0-PG-03 onwards
   records this same WARN per strategy tick:
   ```
   shadow position mark query failed
     error: scan active position: sql: Scan error on column index 3,
     name "chain": converting driver.Value type string ("base") to a
     int: invalid syntax
   ```
   The shadow binary is not blocked by it (the loop continues, the
   smoke stays up). Fix requires either changing `transactions.chain`
   to `TEXT` or making `chainIDToInt` more permissive. Tracked in
   the audit's fix plan §6.2 and every SAFETY_LOCKS_RECHECK.json
   from P0-PG-03 onwards.

   Risk acceptance for Mode A: the WARN is a log noise issue, not a
   data correctness issue. Shadow-mode strategy does not depend on
   `transactions.chain` reads from this scan path. Live mode uses
   different code paths. If Mode A opens, the chain-type fix should
   land within the first 1-2 commits of that work, but it does not
   have to land before Mode A opens.

2. **CI workflow first-run status pending**. The
   `.github/workflows/shadow-smoke-gate.yml` file has been authored
   and statically safety-checked, but it has not yet been executed
   on GitHub Actions (this host has no `act` runner). It will run
   on the next push touching its trigger paths, on `workflow_dispatch`,
   or on the daily cron at 37 6 * * *. A local 180s re-run with the
   same scripts and binaries PASSED.

   Risk acceptance for Mode A: the CI workflow is a gate for future
   regressions. Its first run on GitHub Actions is itself a check
   that the smoke stays green in the canonical CI environment. Mode
   A can open while that first run is pending, with the explicit
   condition that the first CI run must be observed before any
   live / canary binary is actually invoked.

3. **Dual SQL source on disk** (`migrations/postgres/` +
   `internal/adapters/store/postgres/migrator/sql/`). The Go runner
   cannot `go:embed` from outside the package; the embed directory
   is a Makefile-driven copy of the source. This dual source is
   **guarded** by `make check-postgres-migrations-sync`, which is in
   turn a step in `ci.yml`, `migration-quality-gate.yml`, and
   `shadow-smoke-gate.yml`. Collapsing the dual source would
   require either switching the runner to `pressly/goose/v3` or
   moving `migrations/postgres/` into the Go package tree. Both are
   deliberate follow-ups. Recorded in P0-PG-02F and P0-PG-02G.

   Risk acceptance for Mode A: the dual source is operational, not
   theoretical. The CI gate catches any drift. Mode A can open
   without collapsing it.

4. **Live-mode schema guard still separate from shadow-mode schema
   guard**. `ensureLiveSchema` (live / execution-mode-only) and
   `runShadowSchemaGuard` (shadow-mode, added in P0-PG-03B) both
   call `loadLiveSchemaState` + `validateLiveSchemaState`. They
   could be unified behind a single entry point. Recorded in
   P0-PG-03B and P0-PG-04.

   Risk acceptance for Mode A: the two paths share the same
   `loadLiveSchemaState` helper, so the table list stays in sync.
   Mode A can open without unifying them; the unification is a
   refactor that improves clarity, not correctness.

5. **Public RPC health-probe fallback in canonical (non-no-RPC) shadow
   mode**. P0-PG-03B added an explicit no-RPC mode; canonical
   shadow still uses public RPC health probes. This is
   intentional — the canonical shadow is meant to be the
   production-like smoke target. Recorded in P0-PG-03.

   Risk acceptance for Mode A: the no-RPC mode is opt-in via
   `LPBOT_SMOKE_NO_RPC=1`. Canonical shadow keeps the public RPC
   health probes because it needs them to validate the
   network-handling code paths. Mode A can use the canonical
   shadow.

6. **Smoke safety check is a static string-grep**. Records that the
   safety check could be hardened to a process-level assertion
   (e.g. parse the log as JSON and assert structured fields).
   Recorded in P0-PG-03 and P0-PG-03B.

   Risk acceptance for Mode A: the string-grep covers the
   contract that matters (panic / fatal / canary / live / paper /
   signing / broadcast / mint / swap / approve action verbs +
   positive evidence lines). Hardening to structured parsing is
   incremental, not gating.

7. **Pre-existing R1 modified file preserved in working tree**.
   `tests/test_lp_long_horizon_partial_12h_request_v1.py` is a
   tracked modification that has been preserved untouched across
   every P0-PG-* stage, per the user's "不得删除、不得覆盖、不得
   commit" directive. The git working tree still shows it as
   ` M tests/test_lp_long_horizon_partial_12h_request_v1.py`.

   Risk acceptance for Mode A: the file is preserved on the user's
   instruction and does not affect Mode A's engineering work.
   Mode A does not require committing or reverting it; it can
   stay in the working tree until the user explicitly decides
   what to do with it.

8. **CI test race target is narrow** (`./internal/adapters/store/postgres
   ./internal/adapters/rpc`). The audit (P0-PG-01, gap CI-03) noted
   that full-repo `-race` was slow; the canonical P0-PG-01 fix
   landed a focused race target. Recorded in P0-PG-02G.

   Risk acceptance for Mode A: the focused target covers the two
   highest-contention packages (per the canonical comment). Full-repo
   `-race` is intentionally not in the path. Mode A can keep the
   focused target.

## P0-PG-01 audit top-10 blockers — disposition

| ID | Severity | Title | Disposition |
|---|---|---|---|
| BLK-PG-01 | P0 | Missing migration: shadow_decision_trace | Closed (migrations/postgres/000011 added) |
| BLK-PG-02 | P0 | Missing migration: shadow_position_marks | Closed (000013 added) |
| BLK-PG-03 | P0 | Missing migration: shadow_exit_tables | Closed (000014 added) |
| BLK-PG-04 | P0 | 000004 partial-retry risk | Closed (runner-level per-migration transaction in P0-PG-02E; §6.2 flag-column proposal not implemented because the runner-level transaction makes it moot) |
| BLK-PG-05 | P0 | In-Go CREATE TABLE workaround | Closed (migrations consolidated; ensure*Table helpers kept as safety nets; tracked as P2 if anyone wants the second pass) |
| BLK-PG-06 | P0 | lpbot-shadow.service EnvironmentFile | Closed (lpbot-shadow.service + .env.postgres layered; deployed via deploy/systemd/lpbot-shadow.service) |
| BLK-PG-07 | P0 | Migration test gap | Closed (P0-PG-02G migration-quality-gate.yml; P0-PG-04 shadow-smoke-gate.yml) |
| BLK-PG-08 | P0 | Inline CREATE TABLE in cmd/lpbot/main.go:821 | Closed (migrations cover the required tables; loadLiveSchemaState runs in shadow via runShadowSchemaGuard) |
| BLK-PG-09 | P0 | schema_migrations checksum missing | Closed (P0-PG-02E runner records SHA256 checksums) |
| BLK-PG-10 | P0 | make test-race absent | Closed (focused test-race target added; full-repo race run deferred to a later stage if needed) |

All 10 audit P0 blockers are closed. The audit itself remains at
status WARN (top-10 blockers list is informational only; `status`
follows `r1_pause_respected && r2_locked && tiny_canary_allowed
== "no"` which is true here; the WARN comes from the audit's
schema_code_drift_found=true etc. flags which were the entry
condition for P0-PG-02).

## Triage counts

| Level | Count |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 8 (none blocking; all explicitly tracked across canonical stages) |