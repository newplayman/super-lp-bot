# TINY_CANARY_ABORT_CONDITIONS — Tiny Canary Preflight

> **PROPOSED — NOT AUTHORIZED FOR EXECUTION.** This document
> enumerates every condition under which a future
> `*_EXECUTE_V1` tiny canary stage MUST abort. Each condition is
> a hard stop, not a soft warning.

## Pre-execution abort conditions (caught before any chain action)

These are checked before the binary even reaches the
construction-of-tx stage. Any one unsatisfied aborts the run.

1. **`LPBOT_CONFIRM_LIVE` unset**. The live binary's entrypoint
   (`mode_live.go::Run`) requires this env var. Without it, the
   binary exits non-zero with an explicit error message.
2. **Build tag mismatch**. The binary must be built with
   `-tags=live`. If a shadow / dryrun binary is started with
   `LPBOT_CONFIRM_LIVE=YES`, the wallet / broadcaster paths are
   not compiled in and the gate will fail.
3. **`live.enabled=false`** in config. Operator must explicitly
   enable.
4. **`live.kill_switch=true`** in config OR `LPBOT_KILL_SWITCH=1`
   in env. Operator can hard-stop.
5. **Wallet path missing or unreadable**. `cfg.Wallet.KeystorePath`
   empty or `os.Stat` fails.
6. **Wallet passphrase empty**. `cfg.Wallet.Passphrase` empty.
7. **Live wallet address empty or zero**. `cfg.Live.WalletAddress`
   empty or parses to zero address.
8. **Allowed chains empty**. `cfg.Live.AllowedChains` empty.
9. **Allowed pools empty**. `cfg.Live.AllowedPools` empty.
10. **`live.max_order_usd <= 0`** in config.
11. **`live.max_order_usd > 20.0`** (canary hard cap).
12. **`live.daily_loss_limit_usd <= 0`** in config.
13. **`live_risk.max_total_exposure_usd <= 0`** in config.
14. **`live_risk.max_pending_exposure_usd <= 0`** in config.
15. **`live_risk.max_submitted_private_exposure_usd < 0`** in config.
16. **`live_risk.min_gas_reserve_wei < 0`** in config.
17. **`live_risk.max_unreconciled_opening_age_seconds <= 0`** in config.
18. **`execution.npm_base_address` empty**.
19. **Execution backend not configured**. `Execution.Backend` not
    in `{native-rpc, okx-onchain}` OR required credentials for the
    chosen backend are missing.
20. **No RPC**. `chains.base.rpc_primary` empty AND
    `QUICKNODE_API_KEY` empty.
21. **DB schema guard fail**. `ensureLiveSchema` returns
    non-nil; `loadLiveSchemaState` finds any required table
    missing.
22. **Metrics server not started**. `initMetricsServer` returns
    non-nil.
23. **Action count > 1 in the plan**. The runner rejects any
    plan that queues more than one action.
24. **Duration > 15 min**. `timeout --foreground 900` enforces.

## Per-action abort conditions (caught before signing)

These are checked after the runner decides on an action but
before any tx is signed.

25. **Action notional > live.max_order_usd**. The size exceeds
    the configured per-order cap. The runner rejects the action.
26. **Action notional > live_risk.max_pending_exposure_usd**.
    The in-flight exposure would exceed the cap.
27. **Approve amount > live.max_order_usd**. Approves must use
    the exact amount needed (no `ApproveMax` / no unlimited
    approve). The runner checks `ApproveExact` is used and the
    amount matches.
28. **Chain id not in `Live.AllowedChains`**. Reject the action.
29. **Pool id not in `Live.AllowedPools`**. Reject the action.
30. **RPC endpoint not on allowlist**. If the broadcaster
    resolves to a non-public, non-quicknode, non-operator-supplied
    endpoint, reject.

## Per-action abort conditions (caught during signing)

31. **Wallet sign returns error**. Reject; log; abort.
32. **Simulation / gas estimate fails**. Reject; log; abort.
33. **Gas estimate exceeds `live_risk.min_gas_reserve_wei` × 2**
    (heuristic — large gas suggests something abnormal).
34. **Tx simulation returns non-empty revert reason**. Reject;
    log; abort.

## Per-action abort conditions (caught before / during broadcast)

35. **Broadcaster not initialized**. Reject; log; abort.
36. **Broadcaster.Send returns error**. Reject; log; abort.
37. **Submission status indicates failure**. Reject; log; abort.
38. **Tx hash does not match expected pattern** (e.g. all-zero
    hash). Reject; log; abort.
39. **Kill switch flipped during run** (`LPBOT_KILL_SWITCH=1`
    set after the run starts). Reject; log; abort.

## Runtime abort conditions (caught during the bounded window)

40. **Any panic / fatal in the binary's log**. The runner aborts
    on the first panic line.
41. **Any unexpected outbound HTTP request to a non-allowlisted
    host**. The runner maintains a list of allowlisted host
    suffixes; anything else aborts.
42. **Any signing / broadcasting / mint / addLiquidity /
    removeLiquidity / approve / swap / bridge keyword** in the log
    that was NOT expected by the plan. (The plan's expected
    action verbs are recorded before the run starts.)
43. **Runtime exceeds max_duration_minutes (15)** (`timeout`
    SIGTERM). The runner captures the SIGTERM and exits cleanly.
44. **Action count > max_action_count (1)**. The runner enforces
    at the action boundary.

## Post-execution abort / cleanup conditions

45. **PnL / exposure accounting missing**. If the post-action
    record is not in the DB, the runner considers the run a
    partial failure and aborts the cleanup phase.
46. **No receipt / confirmation**. If the broadcaster's Send
    returns success but no receipt is observed within 60s, the
    runner considers the run a partial failure.
47. **Final exposure > max_total_exposure_usd**. After the
    action, the runner re-reads the wallet balance and compares
    to the cap. If exceeded, log + abort.

## Kill switch

The runner must also support an external kill switch:

- Operator sends `SIGTERM` to the runner → clean shutdown.
- Operator sends `SIGINT` → clean shutdown.
- Operator sets `LPBOT_KILL_SWITCH=1` in env → next action aborts
  (the runner checks on every action boundary).

## Rollback plan

If the run aborts at any stage:

- **Pre-broadcast abort**: no chain state changed. No rollback
  needed. Log the blocker; exit non-zero.
- **Post-broadcast partial failure**: the runner records the
  action in `execution_intents` table with status `failed`. The
  intent_id is recorded so a follow-up stage can attempt
  remediation if appropriate. **Tiny canary v1 does NOT attempt
  remediation automatically.** Any remediation is a separate
  stage.
- **Confirmed unexpected exposure**: the runner logs the
  exposure delta, records an alert (`alert_level=p0`), and exits
  non-zero. The live binary's `live.kill_switch` config field is
  flipped to true in the runner's shadow copy (NOT the live
  binary's config). The next run refuses to start until the
  operator explicitly resets.

## What's deliberately NOT an abort condition

- A single transient RPC timeout (the binary's own round-robin
  failover retries on the next available endpoint).
- A single transient DB connection error (the binary's
  pool-reconnect logic handles this).
- A pre-existing chain-type WARN from
  `cmd/lpbot/position_mark.go:220` (audit P0-PG-02-C tracks
  this; not blocking).

These are recorded in the run log but do not abort the run.