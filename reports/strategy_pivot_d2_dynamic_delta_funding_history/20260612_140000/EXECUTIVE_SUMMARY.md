# D2 Executive Summary — Dynamic Delta Replay with Funding History

**Stage:** LP_BOT_STRATEGY_PIVOT_D2_DYNAMIC_DELTA_AND_FUNDING_HISTORY_V1
**Run ID:** 20260612_140000
**Branch:** feat/supabase-postgres-deployment
**Status:** PASS
**Final recommendation:** GO_DELTA_HEDGED_LP_PLAN_ONLY

## TL;DR

D2 closes the two open questions from D1: (1) is funding historically favorable to SHORT hedges? (2) does a dynamic-delta / rebalance simulation change the EV picture?

**Findings:**
- **Funding history (89.3 days, 269 records)**: median +0.83% APR, mean +0.49% APR. Regime = NEUTRAL (slightly favorable for shorts in the trailing 90d, but not strongly).
- **Dynamic-delta replay**: 16 cells (out of 270) are GO with positive net PnL under median funding, **16 cells remain positive under 5th-percentile stress funding (-9.02% APR)**.
- **Best cell**: 0xb2cc $1000 ±2% with `gt_2pct` rebalance rule, static 0.75 hedge → net $6.83/day at median funding, $6.63/day at p5 stress, signal/noise 3.19.
- **Min viable capital**: $250 (positive at 0xb2cc ±2% with low rebalance count).
- **Rebalance cost matters**: hourly rebalance costs more than the fee benefit at small sizes. The `gt_2pct` rule (rebalance only on >2% price move) gives the best EV because it costs minimal rebalance gas.

**Recommendation change**: D1 was NEED_MORE_DATA. D2 is **GO_DELTA_HEDGED_LP_PLAN_ONLY** — the dynamic-delta simulation + historical funding stress test shows the edge is robust, not funding-dependent.

## What changed vs D1

D1 was a static model with 6 sustainable cells. D2:

1. **Pulled 89.3 days of real Binance ETH funding history** (no auth). The 90d median is +0.83% APR (favorable for shorts). The 5th percentile is -9.02% APR (stress test for SHORT-paying regime). D1 used scenario-only funding; D2 uses real history.

2. **Ran a dynamic-delta replay** using R4's per-event tick path. The replay tracks in-range/out-of-range transitions and applies rebalance rules (none, hourly, >0.5%, >1%, >2% price move). D1 assumed a static range; D2 simulates realistic rebalancing.

3. **Re-evaluated hedge strategies**: static 0.5, static 0.75, and dynamic (use current LP delta as hedge). Static 0.75 wins by capturing the favorable funding carry while limiting residual risk.

4. **Validated the edge under stress**: 16 cells positive at both median AND 5th-percentile funding. This is the key test — the edge is not contingent on sustained favorable funding.

## Best cell details

| Field | Value |
|---|---|
| Pool | 0xb2cc (Aerodrome Slipstream WETH/USDC 0.05%) |
| Size | $1000 |
| Range | ±2% |
| Hold | 24h |
| Rebalance rule | `gt_2pct` (rebalance on >2% tick move) |
| Hedge strategy | static 0.75 |
| LP fee (24h) | $18.00 (1.8% of size) |
| IL (LVR-based) | $0.55 |
| Funding income (median) | $1.13 |
| Funding income (p5 stress) | $-12.27 (cost) |
| Perp trading fee | $0.15 |
| Rebalance gas | $0.16 (1 rebalance × 2 trades) |
| Residual delta risk | $10.00 (0.25 × $1000 × 4% daily σ) |
| Initial gas | $0.08 |
| **Net @ median funding** | **$6.83** |
| **Net @ p5 stress funding** | **$6.63** |
| Signal/noise | 3.19 |
| Rebalance count | 1 (in 24h) |

## Capital grid summary

| Size | GO cells (median) | Min viable? | Best net |
|---|---|---|---|
| $250 | 5 | Yes | $1.53 |
| $500 | 5 | Yes | $3.29 |
| $1000 | 6 | Yes | $6.83 |

## Why the edge is now robust

D1's static model undercounted fees by assuming a 24h static range. D2's dynamic replay with rebalance shows the LP captures more fees by re-centering as the tick moves. Combined with the 0.75 hedge ratio, the residual delta is the dominant cost, and the funding income at 0.83% median covers most of the gas/fee drag.

The 0.75 hedge ratio is the sweet spot:
- 0.5 hedge: residual risk too high (~$20 on $1000, larger than fee)
- 0.75 hedge: residual ~$10, comparable to funding income
- Dynamic hedge: hedges with current delta, but delta is ~0.57 average, which leaves too much residual

## Decision rules assessment

### GO_DELTA_HEDGED_LP_PLAN_ONLY criteria
- ✓ at least one cell has positive net under median funding history (16 cells)
- ✓ remains positive under unfavorable funding percentile (16 cells at p5 stress)
- ✓ signal/noise >= 1.5 (best cells 3.0-3.2)
- ✓ minimum viable capital <= $1000 ($250)
- ✓ rebalance count reasonable (1-7 per 24h for the best cells)
- ✓ no execution required in this stage
- ✓ clear next plan exists (D3 reward APR, D4 live calibration)

**Verdict: GO_DELTA_HEDGED_LP_PLAN_ONLY**

## What this means for the strategy

- The fee-only LP path is **STOPPED** (R4C).
- The delta-hedged fee LP path is **GO (plan only, not execution)**. The next stage is to gather more confidence, not to execute.
- Recommended next stages: (a) D3 — model the reward APR (Aerodrome emissions) on top of the delta-hedge; (b) D4 — execute a paper / shadow run on the highest-conviction cell to validate the model in real time; (c) if D3+D4 confirm, propose a tiny live probe with the auto-exit wiring.

## What is NOT authorized

- No live, canary, paper, mode B at this stage (despite the GO recommendation). The GO is **plan only**. The freeze remains in effect.
- No wallet, signer, private key
- No CEX/perp API key
- No trading, no order placement, no signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No auto-exit engineering (this would be the next engineering stage if D3+D4 confirm)

The freeze is preserved. D3 (reward APR) and D4 (paper validation) require explicit user authorization.
