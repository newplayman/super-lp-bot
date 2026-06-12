# D1 Executive Summary — Delta-Hedged LP Feasibility

**Stage:** LP_BOT_STRATEGY_PIVOT_D1_DELTA_HEDGED_LP_FEASIBILITY_V1
**Run ID:** 20260612_120000
**Branch:** feat/supabase-postgres-deployment
**Status:** WARN
**Final recommendation:** NEED_MORE_DATA

## TL;DR

D1 evaluated whether adding a SHORT ETH perp hedge to the R4C-corrected LP position can produce positive EV. The static model finds:

- 6 cells (out of 11,250) are positive under both 0% and +5% APR funding scenarios.
- All 6 sustainable cells are on 0xb2cc (Aerodrome) with ±5% range, 24h hold, 75% hedge.
- Min viable capital: $250 (0.6% net at 0% funding, $0.05; signal/noise ~1.0).
- **However**: current observed ETH funding is **-8% APR** (shorts pay longs). Under current conditions, NO cell is positive.
- Best cell under +20% funding: $1000 ±5% 72h, net = $1.21.

The delta-hedge doesn't rescue the fee-only LP. The edge is real but thin and funding-dependent. Recommendation: **NEED_MORE_DATA** — the model says it's possible but not robust.

## What changed vs R4C

R4C showed that the fee-only LP path doesn't survive proper CLMM math (all 81 cells negative net). D1 asks: can a SHORT ETH hedge + LP fees make the position net-positive? The answer is "barely" under favorable assumptions.

## Top 6 sustainable cells (positive under 0% AND +5% funding)

| Pool | Size | Range | Hold | Hedge | Perp fee | Net @ 0% | Net @ +5% | Net @ +20% |
|---|---|---|---|---|---|---|---|---|
| 0xb2cc | $250 | ±5% | 24h | 0.75 | 0.02% | $0.05 | $0.08 | $0.15 |
| 0xb2cc | $500 | ±5% | 24h | 0.75 | 0.02% | $0.26 | $0.31 | $0.47 |
| 0xb2cc | $500 | ±5% | 24h | 0.75 | 0.05% | $0.15 | $0.20 | $0.35 |
| 0xb2cc | $1000 | ±5% | 24h | 0.75 | 0.02% | $0.68 | $0.78 | $1.09 |
| 0xb2cc | $1000 | ±5% | 24h | 0.75 | 0.05% | $0.45 | $0.56 | $0.86 |
| 0xb2cc | $1000 | ±5% | 24h | 0.75 | 0.10% | $0.08 | $0.18 | $0.49 |

## Why the edge is thin

1. **LP fees are tiny** at $50-$1000 sizing on these pools — only 0.6-1.2% per day on 0xb2cc ±5%.
2. **IL/LVR is real** — even with the realistic LVR-based IL formula, IL is ~0.4% of size per day at ±5% range, comparable to the LP fee.
3. **Hedge cost** is funded by the LP fee plus funding income. At 0% funding, the LP fee barely covers IL + gas + perp fee.
4. **Funding dependence** — the +20% funding scenario is the difference between profitable and unprofitable. Current funding is -8%, opposite direction.

## Decision rules per spec

### GO_DELTA_HEDGED_LP_PLAN_ONLY
- at least one cell has positive net_pnl_hedged_usd: ✓ (6 cells)
- signal_noise_hedged >= 1: marginal (~1.0 at the best cells)
- minimum viable capital <= $1000: ✓ ($250)
- funding scenario remains positive under neutral AND +5% APR funding: ✓
- no execution required: ✓
- clear next plan exists: ✓ (R2 — dynamic-delta simulation, multi-day data)

But the "signal_noise_hedged >= 1" is a near-miss — most cells have signal/noise 0.8-1.2, and the safety margin is thin. The current observed funding would also wipe out the edge.

### NO_GO_DELTA_HEDGED_LP
- no cell positive after hedge costs: ✗ (47 cells positive under favorable funding, 6 under realistic)
- minimum viable capital > $1000: ✗
- funding risk destroys edge: PARTIALLY ✓ (at current -8% funding, all cells negative)
- residual risk too large: ✗ (residual risk is < 5% of size for the $250-$1000 cells)

### PIVOT_REWARD_ONLY_OR_NEW_POOL_ALPHA
- fee-only stopped: ✓
- delta-hedged also not viable at available capital: PARTIALLY — it's marginal, not strictly unviable

The model falls in the middle. Per the spec, **NEED_MORE_DATA** is the right call: model suggests possible edge but funding / dynamic delta / liquidity assumptions are uncertain.

## What this means for the strategy

- The fee-only LP path is **STOPPED** (R4C).
- The delta-hedged fee LP path is **PAUSED** at NEED_MORE_DATA. It could work with:
  - More favorable funding (≥+5% APR sustained)
  - Lower perp fees (Hyperliquid 0.02% taker, OKX 0.03%)
  - Lower IL (volatility drop, looser ranges)
  - Higher capital (more fee to dilute fixed gas cost)
- The recommended next step is R2 (dynamic-delta simulation) before any further capital allocation, not a tiny live probe.

## Safety

- No wallet, no signing, no broadcasting.
- No CEX/perp API key, no order placement.
- No live, canary, paper, or auto-exit engineering.
- Public funding endpoints queried without auth.
- LPBOT_CONFIRM_LIVE not set.
- Freeze preserved.
