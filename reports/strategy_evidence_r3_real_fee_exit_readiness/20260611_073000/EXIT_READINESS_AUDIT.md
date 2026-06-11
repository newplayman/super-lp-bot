# Exit Readiness Audit — R3

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R3_REAL_FEE_ACCRUAL_AND_EXIT_READINESS_V1`
**Run ID:** 20260611_073000
**Audit method:** code read-only, no execution

This audit checks whether the current `lpbot` codebase has the wiring to:
1. Detect a risk event (IL stop, time stop, fee-zero stop, kill switch)
2. Trigger an automatic close of the position (removeLiquidity + collect + burn)
3. Revoke token approvals after close
4. Reconcile the actual on-chain state with the local DB
5. Compute the realized PnL (open / close / fees / gas / IL)

Each row is `EXISTS / PARTIAL / MISSING` with file:line and a blocker_level.

## A. Risk gate — admit-only or auto-close?

The `internal/core/risk` package provides `RiskGate` with the following methods:

| Method | File:line | Purpose | Triggers close? |
|---|---|---|---|
| `Allow(c)` | `internal/core/risk/gate.go:35` | Admit-or-reject a new candidate | NO (returns bool + reason) |
| `IsBlocked(ctx)` | `internal/core/risk/types.go:369` | Read current kill state | NO (passive) |
| `CheckVaR(ctx, total, loss)` | `internal/core/risk/types.go:236` | If loss% >= VaRKillPct, set level=Kill | NO (only sets state) |
| `CheckDrawdown(ctx, peak, cur, weekly)` | `internal/core/risk/types.go:275` | If drawdown >= threshold, set Freeze/Kill | NO (only sets state) |
| `CheckExposure(ctx, exp, budget)` | `internal/core/risk/types.go:319` | If exposure >= MaxExposure, set Warn | NO (only sets state) |
| `RaiseKill(ctx, reason)` | `internal/core/risk/types.go:349` | Manually raise kill switch | NO (only sets state) |
| `LowerWarn(ctx)` | `internal/core/risk/types.go:357` | Manually lower from warn to ok | NO |

**Verdict on risk gate → close wiring: MISSING (blocker_level=P0).**

The risk gate is a **state machine that flips flags**. No code path in `internal/core/risk/`
or `internal/core/loop/` reads a kill flag and calls `OrderManager.Close()`. The only
state-transition side effect is `g.state.Level = ports.KillLevelKill`, which is then
honored by `IsBlocked()` for the next `Allow()` check — but `Allow()` only blocks new
open positions, not existing open positions.

## B. Main loop — does it tick and react to risk?

`internal/core/loop/loop.go`:

- `Run(ctx)` (line 157): Ticker fires every `TickInterval` (default 1m).
- `evaluateStrategies(ctx)` (line 173): stub that increments `IncLoopHeartbeat` and returns.
  **No code reads the current `RiskGate.GetState()` and walks open positions to call `Close`.**

**Verdict on main loop auto-close: MISSING (blocker_level=P0).**

The loop exists but is a heartbeat stub. It does not:
- Walk open positions
- Read risk state
- Trigger Close
- Re-evaluate ranges
- Collect fees

## C. OrderManager.Close — is the close path itself built?

`internal/core/execution/interface.go:240` defines `OrderManager.Close(ExitIntent) ExecutionResult`.
The intent struct (`ExitIntent`, line 89) carries `PositionID, Chain, TokenId, Liquidity, SlippageBps, Deadline, Recipient, Amount0Min, Amount1Min, Reason`.

`internal/core/execution/execution.go:144` (`defaultOrderManager.Close`) implements:
1. Validates `Simulation != nil`
2. Looks up position in `m.positions` map (in-memory state, not DB)
3. Validates status transition `StatusOpen → StatusExiting`
4. Calls `m.txBuilder.BuildRemoveLiquidityTx(ctx, intent)`
5. Calls `m.simulator.SimulateAndValidate`
6. Checks honeypot, slippage, simulation success
7. Updates `pos.Status = StatusClosed` (in memory)

`cmd/lpbot/main.go:2053` (`orderManagerAdapter.Close`) is the production wiring. It:
1. Looks up the position in the DB via `PositionRepo.FindByID`
2. If `liveGate.isExecutionMode()` → calls `o.closeLiveCanaryPosition` (live path)
3. Else: validates status transition, calls `persistShadowAuditTx` (shadow dryrun), then updates DB status to `StatusClosed`

**Verdict on OrderManager.Close implementation: PARTIAL (blocker_level=P1).**

- The interface and execution path are **fully built** in `defaultOrderManager.Close` for shadow mode and in `orderManagerAdapter.Close` for live mode.
- The path runs simulation, validates status transitions, and updates DB. This is good.
- **But there is no caller of this path on a kill event.** The `orderManagerAdapter.Close` is only invoked by external code (loop test, manual CLI). No ticker or risk handler calls it.

## D. Watchdog — does the watchdog force-close?

`internal/core/watchdog/watchdog.go:74` `Run(ctx)` runs checks at intervals. The watchdog
emits alerts but does not call `OrderManager.Close()`. `RunChecks` (line 139) returns
`[]CheckResult` and the parent code (main.go:1149) only logs / sends alerts.

**Verdict on watchdog force-close: MISSING (blocker_level=P1).**

The watchdog detects stuck transactions and emits alerts, but does not trigger close.

## E. Token approval revocation (Invariant #10)

`internal/core/execution/approve.go:263` `BuildRevokeAllowance` exists, called after a
position close in some paths. The live `orderManagerAdapter.Close` path does NOT include
an explicit `BuildRevokeAllowance` step in `cmd/lpbot/main.go:2053-2100`.

**Verdict on approval revocation: PARTIAL (blocker_level=P1).**

The function exists but the live close path does not invoke it. This means after the
`orderManagerAdapter.Close` returns, the token approvals remain granted to the NPM,
which violates invariant #10.

## F. IL stop / time stop / fee-zero stop

| Stop type | Exists? | Where | Triggers close? |
|---|---|---|---|
| IL stop (price out of range) | NO | n/a | n/a |
| Time stop (max hold time) | NO | n/a | n/a |
| Fee-zero stop (no fees for N hours) | NO | n/a | n/a |
| Daily drawdown kill | YES | `risk/types.go:275` | NO |
| VaR kill | YES | `risk/types.go:236` | NO |
| Manual kill switch | YES | `risk/types.go:349` | NO |

**Verdict on LP-specific stops: MISSING (blocker_level=P0).**

The bot has portfolio-level risk gates (drawdown, VaR, exposure) but **no LP-specific
stops** (IL, time, fee-zero). For an LP strategy, the absence of a "out-of-range" stop
is critical: when ETH moves 5% and the position is out of range, the bot keeps the
position open and accrues 0 fees. There is no automated detection or close.

## G. Position reconciliation — is on-chain state trusted?

`internal/core/reconcile/reconcile.go:30` `Reconcile(ctx, chain, walletAddr)` returns a
hardcoded success with zero deviation. The docstring admits:

> "Real full reconciliation can be added in future iterations."

`internal/core/execution/reconcile.go:76` `BootstrapReconcile` is more thorough — it
calls `Chain.ListMyPositions` and `PositionRepo.FindByChainAndStatus`, then compares counts.
But this is **only run at startup**, not on demand. And it does not compare values
(chain positions don't carry a value field).

**Verdict on position reconciliation: PARTIAL (blocker_level=P1).**

- Bootstrap reconcile at startup: exists, runs.
- Periodic reconcile during run: MISSING.
- Value comparison: not implemented.

## H. PnL accounting

`internal/core/pnl/pnl.go:19` `NetPnL(fees, il, gas) = fees - |IL| - gas`. This is the
core formula. `NetPnLBreakdown` (line 35) has `FeeUSD / ILUSD / GasUSD / SwapCostUSD /
SlippageUSD / NetPnLUSD` fields. `VaR` calculation in `var.go` is historical-simulation based.

`internal/core/pnl/fees.go:14` `AccrueFees(pos, swaps)` is the fee accrual formula. It
takes a list of `Swap` events and computes the LP's share. **But it requires the swap
events to be supplied** — there is no in-bot code that subscribes to `Swap` events
from a pool and feeds them to `AccrueFees`. This means **the bot cannot actually compute
realized fees from a position**; it can only compute fees if swaps are externally
imported.

**Verdict on PnL accounting: PARTIAL (blocker_level=P1).**

- Formula exists.
- Inputs (swap events, IL, gas) need to be supplied.
- No automatic subscription to `Swap` events from open positions.

## I. IL computation

`pkg/il/il.go` is a pure library for impermanent loss calculation. The bot can compute
IL if given two price points. But there is no in-loop code that observes position price
and triggers an IL stop.

**Verdict on IL computation: PARTIAL (blocker_level=P2).**

Library exists, not wired into the loop.

## J. Live execution path — does anything actually work in live mode?

`cmd/lpbot/main.go:240` `liveSafetyGate.blockers()` checks 15+ conditions. The current
freeze means the live mode has never been activated. The `closeLiveCanaryPosition` (called
in main.go:2065) is the live close path and is gated by `liveGate.isExecutionMode()`.

**Verdict on live close: EXISTS-but-untested (blocker_level=P1).**

The code is built, but it has never been executed against a real position. The shadow
mode (`persistShadowAuditTx` line 2088) is the only path that has been used.

## K. Summary table

| Component | Status | File:line | Blocker |
|---|---|---|---|
| RiskGate kill state | EXISTS | `internal/core/risk/types.go:104` | none |
| RiskGate kill triggers close | MISSING | (no caller) | **P0** |
| MainLoop ticks | EXISTS | `internal/core/loop/loop.go:157` | none |
| MainLoop walks open positions | MISSING | `internal/core/loop/loop.go:173` (stub) | **P0** |
| OrderManager.Close (interface) | EXISTS | `internal/core/execution/interface.go:279` | none |
| OrderManager.Close (shadow impl) | EXISTS | `internal/core/execution/execution.go:144` | none |
| OrderManager.Close (live adapter) | EXISTS | `cmd/lpbot/main.go:2053` | none |
| LP-specific IL stop | MISSING | n/a | **P0** |
| LP-specific time stop | MISSING | n/a | **P0** |
| LP-specific fee-zero stop | MISSING | n/a | **P0** |
| Watchdog force-close | MISSING | `internal/core/watchdog/watchdog.go:74` (logs only) | **P1** |
| Approval revocation in live close | PARTIAL | `approve.go:263` (exists, not invoked) | **P1** |
| Position reconcile (bootstrap) | EXISTS | `internal/core/execution/reconcile.go:76` | none |
| Position reconcile (periodic) | MISSING | (not implemented) | **P1** |
| Reconcile value comparison | MISSING | `reconcile.go:30` (returns hardcoded success) | **P1** |
| PnL formula | EXISTS | `internal/core/pnl/pnl.go:19` | none |
| PnL input (Swap events) | MISSING | (no subscription) | **P1** |
| IL library | EXISTS | `pkg/il/il.go` | none |
| IL trigger in loop | MISSING | (not wired) | **P2** |
| Live close path | EXISTS | `cmd/lpbot/main.go:2065` (gated) | P1 (untested) |

## L. Final exit-readiness verdict

**Overall: PARTIAL (blocker_level=P0 + P1 + P1).**

The code has all the interfaces, all the close-path logic, and all the simulation /
status / approval primitives required for an automated exit. What it **lacks** is the
**wiring**: no ticker reads the risk state and calls `OrderManager.Close()`. The bot
in its current state would not auto-exit on:

- Daily drawdown breach (RiskGate state flips, but no close)
- Manual kill switch (RaiseKill flips state, but no close)
- IL stop (no such stop exists)
- Time stop (no such stop exists)
- Fee-zero stop (no such stop exists)

**Therefore the only safe way to use this bot for `tiny live` is as a manual-supervised
calibration probe** — a human operator opens the position, monitors the kill state, and
manually invokes `Close` if needed. This is not an autonomous LP strategy.

## M. Re-classification

Based on the audit:

- **GO_TINY_LIVE (autonomous)**: NO. The wiring is missing.
- **CALIBRATION_PROBE_ONLY (manual-supervised)**: POSSIBLE, if a human operator is
  available to monitor and close. The position is open via the existing Open path, and
  the close path is reachable manually.
- **STOP_FEE_ONLY_TINY_LIVE_PATH**: The fee proxy is uncalibrated by R3. R3 cannot
  confirm or refute the R2 expected net. Combined with the missing auto-exit, the
  fee-only path is not safe for autonomous tiny live.
