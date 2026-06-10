# MODE_A_DISCUSSION_DRAFT — P0-PG-06

> **Status**: DRAFT. **Discussion only**. No execution. No runtime.
> This document does not authorize any Mode A action.

---

## 1. Mode A boundary definition

### What Mode A is, in this codebase

Mode A is the first non-shadow runtime mode that exercises anything
beyond pure shadow simulation. Per the canonical shadow binary's
own internal taxonomy (`cmd/lpbot/live_safety_gate_test.go` and the
`liveSafetyGate` blocker list emitted at startup), Mode A lives
**between** shadow and canary:

- **shadow** (`BuildMode == "shadow"`): simulated execution, no
  broadcaster, no wallet, no chain operations. The smoke gate runs
  the shadow binary in this mode for 5 minutes.
- **Mode A** (this draft): a bounded, non-default operational mode
  that observes a runtime target longer than a smoke, optionally
  against public RPC read-only data, but does NOT sign, broadcast,
  or open positions.
- **canary**: real broadcaster wired, real wallet path, $0 nominal
  amount, real chain. Requires explicit LPBOT_CONFIRM_LIVE=YES
  and liveSafetyGate.canaryReadiness() to pass.
- **live**: full broadcaster + wallet + sized positions. Requires
  liveSafetyGate.readiness() to pass.

### What Mode A is NOT

Mode A is **NOT**:

- canary (no real broadcaster)
- live (no wallet-connected run)
- paper trading (no `mode_b` style order-replay engine)
- probe (the probe pipeline is its own LP research stage; not
  promoted by this draft)
- LP strategy execution (no `addLiquidity` / `removeLiquidity` /
  `mint` / `approve` / `swap` / `bridge`)
- tx signing
- tx broadcasting

This stage does NOT start Mode A. The user directive
"完成后不要进入 Mode A" applies. Mode A execution remains
forbidden until ChatGPT review accepts a future
`LP_BOT_ENGINEERING_MODE_A*_*` stage that explicitly authorizes
the execution.

---

## 2. Candidate Mode A scope (three options, no execution)

### Option A1 — bounded shadow supervisor continuity / engineering soak

- **Goal**: verify the shadow binary stays up for 60–120 minutes
  with the hardened no-RPC mode (LPBOT_SMOKE_NO_RPC=1) and exits
  cleanly on SIGTERM. Identical to the P0-PG-04 smoke gate, just
  longer and runs alongside a watcher.
- **Runtime target**: `bin/lpbot-shadow` only. Built once.
- **Duration**: bounded 60–120 minutes.
- **Chain**: none. Public RPC probes are also suppressed via
  no-RPC mode.
- **Data**: persisted to the fresh DB and to the smoke log file.
- **Exit**: clean SIGTERM at end of window; non-zero exit
  requires ChatGPT review of the log.
- **Acceptable for**: closing the "long-running shadow stability"
  open question that the canonical R1 reports left.

### Option A2 — bounded shadow with canonical public RPC read-only probes

- **Goal**: verify the shadow binary's chain-handling code paths
  (the ones the no-RPC smoke bypasses) under a bounded runtime.
- **Runtime target**: `bin/lpbot-shadow` only. Built once.
- **Duration**: bounded 30–60 minutes.
- **Chain**: only the hardcoded public RPC endpoints
  (`mainnet.base.org`, `mainnet-preconf.base.org`,
  `base.drpc.org`). Free, no auth, no signing, read-only
  health checks + read-only public on-chain calls the binary
  already makes.
- **No private RPC, no paid RPC, no auth headers.**
- **Data**: persisted to the fresh DB and to the smoke log file.
- **Exit**: clean SIGTERM at end of window; non-zero exit
  requires ChatGPT review.
- **Acceptable for**: closing the "RPC code path stability" open
  question that the P0-PG-01 audit's GAP-CI-04 raised.

### Option A3 — dryrun-only decision trace replay

- **Goal**: replay the canonical shadow decision-trace pipeline in
  dryrun mode (`-tags=dryrun`) against a fixed input set, to
  verify that the simulator's outputs are deterministic and
  audit-friendly.
- **Runtime target**: `bin/lpbot-dryrun` only. **NOT** shadow,
  **NOT** live. The dryrun binary is built but, per safety
  lock, must not be executed in any canonical stage to date;
  A3 would be the first such execution.
- **Duration**: bounded, per-input replay (probably 5–15 minutes
  total).
- **Chain**: none (dryrun mode does not open RPC adapters).
- **Wallet**: none (dryrun does not import wallet adapters).
- **Data**: persisted to the fresh DB and to a structured log.
- **Exit**: clean exit at end of input set; non-zero exit
  requires ChatGPT review.
- **Acceptable for**: closing the "decision-trace determinism"
  open question that the canonical R1 12h review flagged.

### Explicitly forbidden candidates (NOT up for discussion in this draft)

- canary
- live
- paper / Mode B
- wallet-connected run
- tx signing
- tx broadcasting
- LP `addLiquidity` / `removeLiquidity` / `mint` / `approve` /
  `swap` / `bridge`
- R1 / R2 reopen
- paid RPC
- real secret

---

## 3. P2 risk-acceptance matrix

Eight P2 blockers were carried forward from the P0-PG-05 readiness
review. Each is presented with: (a) whether this draft recommends
accepting it into Mode A discussion, (b) what the risk is, (c)
what the protection is, (d) what triggers abort.

| # | P2 item | Recommend? | Risk | Protection | Abort trigger |
|---|---|---|---|---|---|
| 1 | Pre-existing chain-type WARN from `cmd/lpbot/position_mark.go:220` (audit P0-PG-02-C) | YES | One WARN per strategy tick; log noise; possible future column-type mismatch | The WARN is contained to the shadow strategy tick; live path uses different code; `runShadowSchemaGuard` already fail-closed on missing tables, which is the harder correctness failure | Any uncaught schema error in shadow execution that breaks the strategy loop (currently the loop continues on the WARN); escalate to ChatGPT |
| 2 | CI workflow `shadow-smoke-gate.yml` first-run pending | YES, sequenced | First run may expose runner-image, env-var-escape, or service-port differences from the local container | Local 180s re-run PASSED; the workflow has its own `pg_isready` + `redis-cli ping` waits; static safety check on the workflow file | CI failure; do not retry without ChatGPT review |
| 3 | Dual SQL source on disk (`migrations/postgres/` + `migrator/sql/`) | YES | Drift between the two sources | `make check-postgres-migrations-sync` enforced by every CI workflow and the local Makefile; `migration-quality-gate.yml` step runs it | Sync check fails; the runner refuses to start |
| 4 | Live-mode vs shadow-mode schema guards still split | YES | Schema list drift between the two paths | Both call the same `loadLiveSchemaState` helper; the table list is a single slice | `validateLiveSchemaState` reports missing tables; the binary exits 1 |
| 5 | Public RPC health-probe fallback in canonical (non-no-RPC) shadow mode | YES, A2 only | Outbound HTTP to free public endpoints; no signing, no auth | Only for A2; A1 and A3 use no-RPC mode; the binary does not sign or send tx regardless of RPC availability | The runner's outbound HTTP fails or hits an unexpected status; smoke safety check catches panic / fatal keywords |
| 6 | Smoke safety check is static string-grep | YES | False negatives if the binary's log format changes | Static checks cover the contract (panic, fatal, canary/live/paper keywords, signing/broadcast action verbs, required positive evidence); structure-as-JSON would be incremental | Log content silently changes without the check noticing; review CI workflow runs every PR touching the smoke scripts |
| 7 | Pre-existing R1 modified file preserved in working tree | YES (unchanged) | None | User directive preserves it; not touched by any canonical stage; not touched by this draft | n/a |
| 8 | CI test race target is narrow | YES | Full-repo `-race` not in CI | Focused target covers the two highest-contention packages; this is the canonical decision per the test-race comment in the Makefile | Test flake from a different package; ChatGPT decides whether to expand the target |

---

## 4. Proposed Mode A safety contract

If a future stage is approved by ChatGPT, that stage must satisfy:

- **max duration**: bounded. A1 ≤ 120 min, A2 ≤ 60 min, A3 ≤ 15 min.
- **no wallet**: no `internal/adapters/wallet/...` import path
  activated. `LPBOT_CONFIRM_LIVE` MUST NOT be set.
- **no signing**: no keypair loaded; no `crypto/ecdsa`, no
  `crypto/ed25519` paths touched.
- **no broadcast**: no `sendTransaction`, no `broadcast`, no
  `submit`, no `MevSubmitter` invoked.
- **no live / canary / paper**: dryrun or shadow mode only;
  `BuildMode != "live"`; no `canary_cycle.sh` invocation.
- **no paid RPC**: only free public endpoints (if any); no
  QuickNode, no Alchemy, no Infura, no private RPC.
- **no R1 / R2 reopen**: R1 stays PAUSED; R2 stays LOCKED; the
  `r1_pause_respected` / `r2_locked` safety checks must pass.
- **logs/artifacts required**: stdout+stderr captured to a
  timestamped log file; report dir with `FINAL_VERDICT.json`,
  `SAFETY_LOCKS_RECHECK.json`, raw log, and a `MODE_A_*-SUMMARY.md`.
- **abort conditions**:
  - panic / fatal in the log
  - schema_guard=fail
  - any `smoke_no_rpc_mode=false` when expected true
  - any `LPBOT_CONFIRM_LIVE=YES` env var accidentally set
  - any signing / broadcasting action keyword in the log
  - any unexpected outbound HTTP request to a non-allowlisted host
- **success criteria**: log shows clean startup + sustained
  worker activity + clean SIGTERM shutdown; safety check PASS;
  no schema_guard=fail; required positive evidence lines present
  (where the variant includes a schema guard, e.g. A2/A3 with
  fresh DB).
- **fail criteria**: any abort condition above; any non-zero exit
  not attributable to a planned timeout.

---

## 5. Recommended next real-execution stage

This is a **plan**, not an execution. Execution requires a separate
stage that explicitly names the option (A1 / A2 / A3) and is
reviewed by ChatGPT.

Recommended name:

```
LP_BOT_ENGINEERING_MODE_A1_SHADOW_CONTINUITY_SOAK_PLAN_V1
```

(Or `MODE_A2_*` or `MODE_A3_*` — these are the only three options
this draft proposes.)

That plan stage would contain:

- exact duration (e.g. 60 minutes)
- exact log / report output paths
- exact abort conditions (mirroring this draft)
- exact ChatGPT-review acceptance path

Mode A execution itself remains forbidden until a future stage
that includes the string `EXECUTE` in its name (e.g.
`LP_BOT_ENGINEERING_MODE_A1_SHADOW_CONTINUITY_SOAK_EXECUTE_V1`)
and is reviewed by ChatGPT.

---

## Appendix: explicit ChatGPT-review checkpoints

Before any Mode A execution:

1. **ChatGPT reviews this MODE_A_DISCUSSION_DRAFT.md** (already
   on remote after this commit lands).
2. **ChatGPT reviews a plan stage** (e.g. `MODE_A1_*_PLAN_V1`).
3. **ChatGPT reviews an execute stage** (e.g.
   `MODE_A1_*_EXECUTE_V1`) **and** the user explicitly
   authorizes execution in the prompt that triggers that stage.

This three-stage gating is deliberate: the discussion is cheap, the
plan is structured, the execute is bounded and time-boxed. None of
the three are skippable.