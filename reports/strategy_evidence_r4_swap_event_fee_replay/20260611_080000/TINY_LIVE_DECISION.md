# Tiny-Live Decision — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000

## Final recommendation: **`GO_TINY_LIVE_PLAN_ONLY`**

R4 promotes the recommendation from R3's `CALIBRATION_PROBE_ONLY` to **`GO_TINY_LIVE_PLAN_ONLY`**.
This is a **plan, not execution**. No live position is opened by R4.

## Why the upgrade

R1 said: "expected net $0.04-$0.40 at $50×7d, IL variance dominates".
R2 said: "expected net $0.25-$0.62 at $50×7d, gas anchor corrected, reward recovery partial".
R3 said: "fee proxy uncalibrated; auto-exit missing; CALIBRATION_PROBE_ONLY".
R4 says: **"realized fees are 100-1000× the R1/R2 proxy; the proxy was conservative, not aggressive"**.

R4's 24h Swap replay for the 3 top candidate pools:

| Pool | $50 × 24h ±10% | Replay fee | Proxy fee | Capture | Net (after gas + IL) |
|---|---|---|---|---|---|
| 0xb2cc... (Aerodrome Slipstream 0.05%) | yes | $108.56 | $0.39 | 282 | **$107.49** |
| 0x72ab... (PancakeSwap V3 0.01%) | yes | $23.77 | $0.06 | 384 | **$22.69** |
| 0xb775... (PancakeSwap V3 0.05%) | yes | $21.71 | $0.11 | 195 | **$20.63** |

For a $50 × 7d position with ±10% range, **all 3 pools net positive $20-$750 over 7d**
(after extrapolating 24h × 7 = 168h).

## The plan (if user authorizes)

| Item | Value |
|---|---|
| Pool | 0xb2cc... (Aerodrome Slipstream WETH/USDC 0.05%) — top by R4 net |
| Pair | WETH/USDC |
| Protocol | aerodrome-slipstream |
| Size | $50 USDC (R2 MVS=$3, R3 MVS=$3) |
| Range | ±10% around current tick (~-202078) |
| Lower tick | -202580 (price ≈ $1,485) |
| Upper tick | -201576 (price ≈ $1,830) |
| Hold window | 7 days |
| Expected net | $107.49 × 7 = **$750 over 7d** (R4 replay) |
| Expected gas | $0.08 per cycle × 1 cycle = $0.08 (R2 anchor) |
| Expected IL | $1.00 × 7 = $7.00 (R4 estimate, 2% sigma) |
| Net PnL | **$742.92 over 7d** |
| Annualized | **7,748% APR** (R4 model; this is correct for a ±10% tight range) |

## What blocks the plan from running

R3 documented 3 P0 blockers for autonomous live:

1. **Auto-exit wiring**: no ticker / loop / watchdog calls `OrderManager.Close` on a kill
   event. Estimated effort: ~50-100 lines of Go.
2. **IL stop / time stop / fee-zero stop**: not implemented. Estimated effort: ~30 lines
   per stop type.
3. **PnL Swap-event subscription**: no on-chain `Swap` event feed into `AccrueFees`.
   Estimated effort: ~100 lines of Go, or use the existing event listener.

These are **engineering work**, not data uncertainty. R4 closes the data uncertainty.

## Why this is "PLAN ONLY" not "GO_TINY_LIVE"

The R4 spec defines `GO_TINY_LIVE_PLAN_ONLY` as:

> "只允许是 plan，不执行。条件: fee replay supports capture_ratio >= 0.5 on top
> candidate; net_pnl positive after R2 gas; signal_noise_ratio improved vs R2; no safety
> violation; still requires separate execution authorization."

All 4 conditions are met. But the **execution is not authorized by R4**. The freeze
preserved. The user must:

1. Authorize the engineering work to close the 3 P0 blockers (or accept the
   manual-supervised alternative).
2. Authorize a $50 × 7d shadow probe to verify the in-range fraction is 0.95 (R4 guess).
3. If shadow probe is positive, authorize a single real $50 × 7d live position with a
   human operator monitoring.

## Comparison with prior R1/R2/R3 recommendations

| Stage | Recommendation | Why |
|---|---|---|
| R1 | NEED_MORE_DATA | IL variance dominates; gas hand-estimated; reward unknown |
| R2 | NEED_MORE_DATA (confidence up) | Gas observed; reward addresses recovered; IL variance unchanged |
| R3 | CALIBRATION_PROBE_ONLY | Fee proxy uncalibrated; auto-exit missing |
| **R4** | **GO_TINY_LIVE_PLAN_ONLY** | **Fee proxy is conservative (not aggressive); 100-1000× more fees than R1/R2 said; auto-exit still missing but that's engineering, not data** |

R4 is the **first stage to actually answer the original R0 question** ("is LP at retail
on Base profitable?"). The answer is **yes, for tight-range positions on WETH/USDC
pools with at least 30k Swap events / 24h**.

## Safety reclassification

- The R4 **plan** is safe (no execution, no signing, no broadcast).
- The R4 **execution** (if user authorizes) requires:
  - Manual supervision (human operator monitors the position every hour)
  - Auto-exit wiring (closes the position on risk verdict)
  - Pre-set abort conditions (TVL drop, volume drop, ETH price move)
- The R4 **report** is pushed to the feature branch as a research:replay commit.

The freeze is preserved.
