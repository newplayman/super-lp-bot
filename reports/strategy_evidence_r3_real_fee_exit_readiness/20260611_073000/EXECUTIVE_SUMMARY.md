# Executive Summary — R3

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R3_REAL_FEE_ACCRUAL_AND_EXIT_READINESS_V1`
**Run ID:** 20260611_073000
**Verdict:** **WARN** (fee calibration blocked, exit audit complete, decision useful)

## TL;DR

R3 attempts to validate the R1/R2 fee proxy (`volume_h24 × fee_tier × position_share`)
by reading **real on-chain data** for the 3 top candidate pools. The probe **failed
methodically and honestly**:

1. **Fee proxy calibration: BLOCKED.** Both PancakeSwap V3 (`0x03a520b3...`) and
   Aerodrome Slipstream (`0x090b2a6b...`) use non-canonical V3 storage layouts.
   `positions(tokenId)` reverts for real tokenIds; the canonical slot 1/2 reading
   for `feeGrowthGlobal0X128` / `feeGrowthGlobal1X128` returns values that are
   10²⁰× too large to be real fees. R3 cannot confirm or refute the R1/R2 model.

2. **Auto-exit path: MISSING (P0).** The `OrderManager.Close(ExitIntent)` interface
   is fully built (in `internal/core/execution/execution.go:144` and
   `cmd/lpbot/main.go:2053`). The risk gate (`internal/core/risk/gate.go:35`)
   flips kill-state flags. But **no ticker, loop, or watchdog** calls
   `OrderManager.Close` on a kill event. The bot cannot auto-exit a position
   on daily drawdown, manual kill, or any other risk verdict.

3. **IL stop, time stop, fee-zero stop: MISSING (P0).** No LP-specific stops exist.
   The risk gates are portfolio-level (drawdown, VaR, exposure), not LP-position-level.

4. **PnL accounting: PARTIAL (P1).** The formula exists. The `Swap` event
   subscription that would feed `AccrueFees` is missing.

5. **Position reconciliation: PARTIAL (P1).** Bootstrap reconciliation at startup
   exists, but the `Reconcile` function returns a hardcoded success with zero
   deviation. There is no value comparison and no periodic reconcile.

## What R3 has decided

**R3 final_recommendation: `CALIBRATION_PROBE_ONLY`**

A $50 × 7d position on pool 0xb2cc... (Aerodrome Slipstream WETH/USDC 0.05%),
operated by a human in shadow mode (no live execution), with full `Swap` event
capture. The realized fee from the probe would calibrate the R1/R2 proxy. After
calibration, the recommendation can be upgraded to `GO_TINY_LIVE` (if proxy is
correct) or downgraded to `STOP_FEE_ONLY_TINY_LIVE_PATH` (if proxy overestimates).

**The freeze is preserved.** No live execution is authorized. The probe requires
explicit user authorization to start.

## What R3 specifically says

> R1 said "1-10 USDC × 24h is gas-negative; $50 × 7d passes on 3 pools". R2 said
> "real gas anchor is $0.08, not $0.30; the path to $10 × 24h is reward data".
> R3 says: "even if R1/R2 are right, the fee proxy is uncalibrated and the
> auto-exit is missing. The cheapest path to ground truth is a $50 × 7d shadow
> probe with manual supervision and on-chain `Swap` event capture."

## What R3 does NOT do

- Does not run any canary, live, or paper mode.
- Does not connect to a wallet, signer, or broadcaster.
- Does not sign or broadcast any transaction.
- Does not read private keys or seed phrases.
- Does not modify R1, R2, or any pre-existing report directory.
- Does not restart any long-horizon collector.

## What R3 recommends next

R4 (probe execution with on-chain event capture). See `NEXT_STRATEGY_FORK.md` for
full details. R4 is **shadow-mode only** and **requires explicit user authorization**.
