# KILL_SWITCH_AND_ROLLBACK_PLAN — Tiny Canary Preflight

> **PROPOSED — NOT AUTHORIZED FOR EXECUTION.**

## Goal

Define the kill-switch and rollback plan for tiny canary v1.
The kill switch is the operator's primary abort path; the rollback
plan is the post-action recovery procedure.

## Kill switch (operator-controlled)

### Three independent paths

The operator can kill the canary run via any of:

1. **`SIGTERM` / `SIGINT` to the runner process**. The runner
   forwards to the binary via `ctx.Done()`; the binary's
   `runShadowOutcomeLoop` and `runStrategyLoop` exit cleanly on
   the next iteration.
2. **`LPBOT_KILL_SWITCH=1` env var on the runner**. The
   runner checks this env var on every action boundary. If set
   at any boundary, the runner refuses to proceed and the binary's
   `liveSafetyGate.blockers()` returns
   `"live.kill_switch=true"` on its next refresh.
3. **`live.kill_switch=true` in the live config file**. The
   binary's `liveSafetyGate` reads this on startup and refreshes
   it on every config reload (if any). A config edit that flips
   `live.kill_switch=true` blocks the next action.

### Kill-switch semantics

- A kill switch flip does NOT retroactively cancel an in-flight
  tx. If the binary has already broadcast and is waiting for the
  receipt, the receipt will still arrive. The kill switch only
  blocks the *next* action.
- A kill switch flip does NOT affect already-applied LP actions.
  If the binary already added liquidity, that liquidity remains
  on-chain. Removal is a separate manual operation (out of scope
  for tiny canary v1).
- A kill switch flip during the pre-action phase aborts the
  run with exit 130 (SIGINT) or 143 (SIGTERM) plus an extra
  log line `"kill switch triggered; aborting run"`.

### Operator-side procedures

- The operator is expected to monitor the run log in real time.
- On any abort signal, the operator records the exit code and
  the last log line.
- A subsequent run cannot start until the operator explicitly
  resets the kill switch (`LPBOT_KILL_SWITCH=` empty, config
  `live.kill_switch=false`).

## Rollback plan

### Pre-broadcast abort

- No chain state changed. No rollback needed.
- The runner logs the blocker and exits non-zero.
- The intent record (if any was created) is left in the
  `execution_intents` table with status `failed` for traceability.

### Post-broadcast partial failure

- The runner records the action in `execution_intents` with
  status `failed` and the broadcast tx hash (if any).
- The intent_id is logged so a follow-up stage can attempt
  remediation if appropriate.
- **Tiny canary v1 does NOT attempt remediation automatically.**
  Any remediation is a separate stage.

### Post-action confirmed unexpected exposure

If the post-action balance check shows:

- Wallet USDC balance decreased by more than `live.max_order_usd
  + gas` → unexpected exposure.
- LP position count increased (i.e. an LP action happened without
  being in the plan) → unexpected exposure.

The runner:

1. Logs the unexpected delta with `alert_level=p0`,
   `alert_src=tiny_canary_overshoot`.
2. Records the incident in `execution_intents` with status
   `overshoot`.
3. Sets the runner's local kill switch (does NOT modify the
   live binary's config; the runner's kill switch is a local
   override).
4. Exits non-zero with exit code 99 (custom: "tiny canary
   overshoot").

A follow-up stage must:

1. Inspect the on-chain state (USDC balance, LP positions).
2. Manually drain or unwind positions if the operator
   authorizes.
3. Update the plan to reduce the per-action cap.
4. Re-run with a fresh keystore if compromise is suspected.

### Wallet compromise suspected

If the operator at any time suspects wallet compromise:

1. `LPBOT_KILL_SWITCH=1` (immediate).
2. Move remaining USDC / WETH / LP positions OUT OF THE WALLET
   using a separate, manually-controlled tool. This is a manual
   procedure outside the lp-bot runtime.
3. Rotate the keystore (generate a new wallet, fund it, update
   `cfg.Wallet.KeystorePath`).
4. Open a follow-up stage named
   `LP_BOT_ENGINEERING_POST_INCIDENT_REVIEW_V1` for analysis.

## What the kill switch does NOT do

- Does NOT cancel already-broadcast txs.
- Does NOT undo on-chain state changes.
- Does NOT drain wallet balances.
- Does NOT replace a manual incident response.

These are deliberate. The kill switch is a fast abort, not a
reversal mechanism. Reversal requires operator action.