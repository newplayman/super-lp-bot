# D2 Dynamic Delta Model

## Goal

Replace D1's static-range assumption with a per-event rebalance-aware replay using R4's tick path. Replace D1's scenario-only funding with real Binance funding history. Validate the edge under stress.

## Model overview

For each (pool, size, range, rebal_rule, hedge_strategy) cell:
1. Load R4's per-event Swap data for the 24h window.
2. Track the LP position's current range [tickLower, tickUpper] and re-center when the rebal rule fires.
3. Per event:
   - If current tick in range: accrue LP fee (from R4C fee_per_dollar_per_day) and LVR-based IL.
   - If out of range: no fee, no IL.
4. Apply funding income (real median from 89.3d history) over the 24h hold.
5. Apply rebalance gas (1 gas cycle per rebalance × 2 = LP + perp trade).
6. Apply residual delta risk (1 - hedge_ratio) × size × σ_window.
7. Compute net PnL hedged and signal/noise.

## Grid (270 cells)

- **Pools** (2): 0xb2cc (Aerodrome 0.05%), 0x72ab (PancakeSwap 0.01%)
- **Sizes** (3): $250, $500, $1000
- **Ranges** (3): ±2%, ±5%, ±10%
- **Rebalance rules** (5): none, hourly, >0.5%, >1%, >2% price move
- **Hedge strategies** (3): static 0.5, static 0.75, dynamic (use current LP delta)
- 2 × 3 × 3 × 5 × 3 = 270 cells

## Funding source

- **Source**: Binance public `fapi/v1/fundingRate?symbol=ETHUSDT`
- **Auth**: none
- **Records**: 269 (89.3 days, 8h cadence)
- **Statistics**:
  - Mean: +0.49% APR
  - Median: +0.83% APR
  - Stddev: 6.17%
  - 5th percentile: -9.02% APR
  - 95th percentile: +9.59% APR
  - % time shorts pay: 43.5%
  - % time shorts receive: 56.5%
  - Max adverse streak: 16 8h periods = 128 hours
- **Regime label**: NEUTRAL

D2 uses the **median** as the base case. D2 also stress-tests at p5 (-9.02% APR) — see stress test in FINAL_VERDICT.

## LP fee model

Each cell distributes `size × fee_per_dollar_per_day` over `n_total` events. Per-event fee = `size × fee_per_dollar_per_day / n_total`. Summed over all in-range events, the total fee equals the daily fee × in-range fraction (since only in-range events accrue fee).

## IL model

LVR-based: `il_step = size × 0.5 × σ² × period_days` accumulated only over in-range periods. The model integrates IL over time, not per event. Out-of-range periods have zero IL.

## Rebalance gas

1 gas cycle per rebalance × 2 (LP tx + perp trade). For `gt_2pct` rule on 0xb2cc ±2%: 1 rebalance in 24h × 2 = $0.16. For `gt_0.5pct` rule: 35 rebalances × 2 = $5.55, which can dominate the net PnL at small sizes.

## Dynamic hedge strategy

The LP's ETH delta varies with the tick position:
- At tickLower: 0% ETH, 100% USDC
- At midpoint: 50% ETH
- At tickUpper: 100% ETH, 0% USDC

The dynamic hedge uses the average LP delta over the 24h window as the hedge ratio. For 0xb2cc: avg delta = 0.575, so dynamic hedge ≈ 57.5% of notional. This is less than 0.75, leaving more residual risk.

The dynamic strategy gave 0/90 positive cells in D2. The reason: at 0.575 hedge, residual is 0.425 × $1000 × 0.04 = $17, which is larger than the fee. Static 0.75 wins because the funding income at +0.83% APR is enough to cover the 25% unhedge's residual.

## Signal/noise

`signal = max(fee - il, 1e-9)`
`noise = max(il × 0.5 + residual × 0.5, 1e-6)`
`signal_noise = signal / noise`

Best cells: 3.0-3.2. D2 spec threshold: >= 1.5 for GO.

## Decision rules

- **GO**: net_hedged > 0 AND signal_noise > 1.5 AND size <= 1000 AND rebal_count < 30
- **NEED_MORE_DATA**: net_hedged > -0.1
- **NO_GO**: net_hedged <= -0.1

## Limitations

- The model is 1-day; longer holds would accumulate more fees but also more rebalance gas.
- Rebalance cost is 1 gas cycle × 2 (LP + perp); actual cost could be 1.5-2× for tight ranges.
- The dynamic hedge is approximated as the time-average LP delta, not recomputed per event.
- The funding income uses median 90d rate; actual funding during the 24h hold would vary.
- Out-of-range period's "no fee, no IL" is a simplification — the LP could still earn fees on the one-sided token if a swap moves price back into range.

## Stress test

Re-running the model with funding_apr = -9.02% (5th percentile of 90d history) keeps 16 cells positive. The best cell remains $1000 ±2% 0xb2cc with $6.63/day (vs $6.83/day at median). The edge survives the worst-case 5% of the historical funding regime.
