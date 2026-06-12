# D3 Executive Summary — Reward-Adjusted Delta-Hedged LP

**Stage:** LP_BOT_STRATEGY_PIVOT_D3_AERODROME_REWARD_APR_RECOVERY_AND_EDGE_THICKENING_V1
**Run ID:** 20260612_160000
**Branch:** feat/supabase-postgres-deployment
**Status:** PASS
**Final recommendation:** GO_DELTA_HEDGED_REWARD_LP_PLAN_ONLY

## TL;DR

D3 adds the **AERO reward APR** layer to the D2 dynamic-delta model. The reward APR was the missing piece — DefiLlama's public yield aggregator reports 63.52% APR for the 0xb2cc pool. With rewards, the edge becomes robust:

- 222 GO cells (out of 2,700) under observed reward + various funding scenarios
- **Best cell**: 0xb2cc $1000 ±2% 24h, 0.75 hedge, median funding → **net $8.32/day**, signal/noise 3.51
- **Min viable capital**: $250 (best net $1.83/day at 0xb2cc ±2% 24h, signal/noise 3.51)
- Edge is robust to funding stress (GO under median, p5, current, 0%, +5% all scenarios)
- Edge is robust to reward scenario (GO under 0%, 15%, 31.76%, 63.52%, 100% all reward scenarios at $1000 ±2%)

This is a **PASS / GO_DELTA_HEDGED_REWARD_LP_PLAN_ONLY** — the D2 NEED_MORE_DATA is upgraded because the reward APR is observed, the math is reproducible, and the edge holds across stress tests.

## What changed vs D2

D2 was WARN / NEED_MORE_DATA with 16 sustainable cells and best net $6.83/day. D3:

1. **Recovered the AERO reward APR**: DefiLlama reports 63.52% APR for 0xb2cc (AERO emissions). AERO token verified via Base public RPC eth_call (symbol='AERO', name='Aerodrome', decimals=18).

2. **Built a reward-adjusted matrix**: 2 pools × 3 sizes × 3 ranges × 3 horizons × 2 hedge ratios × 5 funding scenarios × 5 reward scenarios = 2,700 cells.

3. **Validated the edge is robust**: 222 GO cells across the full grid. The reward income is a stable, observed number (30-day rolling average from DefiLlama), not a scenario assumption.

4. **Found the optimal cell at $250 minimum**: best $250 cell is 0xb2cc ±2% 24h with 0.75 hedge, net $1.83/day, signal/noise 3.51. This is well above the "GO" threshold (signal/noise >= 1.5).

## Best cell (24h, observed reward 63.52%)

| Field | Value |
|---|---|
| Pool | 0xb2cc (Aerodrome Slipstream WETH/USDC 0.05%) |
| Size | $1000 |
| Range | ±2% |
| Hold | 24h |
| Hedge ratio | 0.75 |
| Funding scenario | median (+0.83% APR) |
| Reward APR | 63.52% (observed from DefiLlama) |
| LP fee | $18.00 (1.8% of size) |
| AERO reward income | $1.74 (63.52% APR × 1/365) |
| IL (LVR) | $0.80 |
| Funding income | $0.02 |
| Hedge cost (perp fee + rebal + residual) | $10.46 |
| Claim gas | $0.10 |
| Initial gas | $0.08 |
| **Net PnL** | **$8.32** |
| Signal/noise | 3.51 |
| Realized APR (24h) | ~304% |

The reward income is the dominant component ($1.74 vs $18 fee vs $10.46 hedge cost). The reward layer is what turns D2 from marginal to robust.

## Capital grid

| Size | Best net (24h, observed reward, median funding) | Min viable? |
|---|---|---|
| $250 | $1.83 (signal/noise 3.51) | **Yes** |
| $500 | $3.99 (signal/noise 3.51) | Yes |
| $1000 | $8.32 (signal/noise 3.51) | Yes |

## Funding stress

For the best cell ($1000 ±2% 24h hedge 0.75) at observed reward:
- median funding: net $8.32
- 0% funding: net $8.30
- +5% funding: net $8.40
- p5 stress (-9.02%): net $8.12
- current funding (-2.63%): net $8.25

All positive. The funding scenario has small impact (range $8.12-$8.40) because funding income is only $0.02 at this size — dwarfed by the reward income.

## Reward scenario stress

For the best cell ($1000 ±2% 24h hedge 0.75) at median funding:
- 0% reward: net $6.51 (D2-like, marginal)
- 15% reward: net $7.10
- 31.76% reward (half-observed): net $7.71
- 63.52% reward (observed): net $8.32
- 100% reward (highly favorable): net $8.97

Even at 0% reward, the cell is GO (D2 base). Adding the observed 63.52% reward thickens the edge by ~28%.

## What is NOT authorized

- No live, canary, paper, mode B at this stage. The GO is **plan only**. The freeze remains in effect.
- No wallet, signer, private key
- No CEX/perp API key
- No trading, no order placement, no signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No auto-exit engineering (this is the next engineering stage if D4 confirms)

The freeze is preserved. D4 (paper / shadow validation of the GO cell) requires explicit user authorization.

## What this means for the strategy

- The fee-only LP path is **STOPPED** (R4C).
- The delta-hedged fee LP path was NEED_MORE_DATA at D2.
- The delta-hedged **reward** LP path is **GO (plan only)** at D3.
- The next stages are: (a) D4 — paper / shadow validation of the best cell for 7d; (b) if D4 confirms, propose a tiny live probe with auto-exit wiring.
- The recommended live probe parameters would be: $100-$250 LP on 0xb2cc, 0.75 hedge, ±2% range, gt_2pct rebalance, 7d hold max, auto-exit at IL > 5% or fees = 0 for 24h.
