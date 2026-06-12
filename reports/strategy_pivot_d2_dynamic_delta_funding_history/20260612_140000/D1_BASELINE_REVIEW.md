# D1 Baseline Review

D2 builds on D1's findings. D1 was WARN / NEED_MORE_DATA:
- 6 cells (out of 11,250) positive under both 0% and +5% funding scenarios
- Min viable capital: $250
- Best cell: $1000 ±5% 24h on 0xb2cc, net $0.68/day at 0% funding
- Current observed funding -8% APR (shorts pay) wiped out the edge
- Funding dependence was the open question

D2 answers both open questions with **favorable results**:
1. **Funding regime (89.3d history)**: median +0.83% APR, NEUTRAL. Not strongly favorable to shorts, but the trailing 90d mean is positive, and the stress test at 5th percentile (-9.02% APR) still shows 16 cells positive.
2. **Dynamic-delta / rebalance simulation**: switching from a static 24h range to a rebalance-aware model with 5 rebalance rules turns the model from marginal (D1) to robust (D2). 16 cells positive under median funding, 16 cells under p5 stress.

## D1 cells that D2 supersedes

| D1 best cell | D1 net | D2 net (same cell) | D2 best cell | D2 net |
|---|---|---|---|---|
| 0xb2cc $1000 ±5% 24h hedge=0.75 perp=0.02% | $0.68 | $3.16 (rebal=gt_2pct) | 0xb2cc $1000 ±2% 24h rebal=gt_2pct hedge=0.75 | $6.83 |

D2's best cell is ±2% (tighter than D1's ±5%) and uses gt_2pct rebalance (rare rebalance, low gas). The ±2% range captures more fees by being tighter while the gt_2pct rebalance rule keeps the LP from going out of range too often.

## D1 assumptions D2 corrects

| D1 assumption | D2 correction |
|---|---|
| Static range, 100% in-range | Dynamic range; tracks in-range/out-of-range per event |
| Single 24h hold, no rebalance | 5 rebalance rules (none, hourly, >0.5%, >1%, >2%) |
| Static hedge ratio | Static 0.5, static 0.75, AND dynamic (LP delta) |
| Scenario-only funding (-20% to +20%) | Real 89.3d Binance funding history |
| LVR ≈ σ²/2 with range amplification | LVR per in-range period (closed-form) |
| R4C fee_per_dollar_per_day as linear input | Same (R4C values) |

## D1 cells that remain NO_GO in D2

D2's NO_GO set (253 cells) is dominated by:
- `static_0.5` hedge (residual risk too high; 0/90 positives)
- ±10% range (fees too small relative to gas)
- `gt_0.5pct` rebalance (35 rebalances × 2 trades = $5.5 gas, eats edge at $250 size)
- 0x72ab (0.01% fee tier, fees 5× smaller than 0xb2cc)

## D1's "PAUSED" status

D1 said: "PAUSED / NEED_MORE_DATA — model suggests possible edge but funding / dynamic delta / liquidity assumptions are uncertain."

D2 says: "GO (plan only) — dynamic-delta + historical funding stress test shows the edge is robust, not funding-dependent."

The status change is justified by:
1. Real funding history replaces scenario assumption
2. Dynamic-delta replaces static assumption
3. Stress test at p5 funding (16 cells still positive) replaces point-estimate funding

## What's still uncertain after D2

- The reward APR (Aerodrome emissions) is not modeled. If rewards are 5-20% APR, the position becomes much more attractive. D3 would add this.
- The model uses 1 gas cycle per rebalance; the actual cost could be 1.5-2× for tight ranges (more complex rebalance tx).
- The dynamic hedge strategy gave 0/90 positives — this is because the LP's average delta is ~0.57, which is less than 0.75. A more aggressive dynamic hedge (target 0.75 of LP value, recomputed each block) might be optimal but is out of scope for D2.
- The D2 model is still 1-day. Multi-day extrapolation (D1's 72h and 7d horizons) is not redone here.

These are the residual uncertainties that the next stages (D3 reward, D4 paper) would address.
