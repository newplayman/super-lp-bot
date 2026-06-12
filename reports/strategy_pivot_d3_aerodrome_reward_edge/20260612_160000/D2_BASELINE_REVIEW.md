# D2 Baseline Review

D3 builds on D2. D2 was PASS / GO_DELTA_HEDGED_LP_PLAN_ONLY with:
- 16 sustainable cells under both median and p5 stress funding
- Best cell: $1000 ±2% 24h, 0.75 hedge, gt_2pct rebalance, net $6.83/day at median funding
- Min viable: $250 (0xb2cc ±2% 24h, hedge 0.75)

D2 was an improvement over D1 (which was NEED_MORE_DATA) thanks to:
1. Real 89.3d Binance funding history (D1 was scenario-only)
2. Dynamic-delta replay with 5 rebalance rules (D1 was static)
3. Stress test at p5 funding showed 16 cells remain positive

D2's open question was the reward layer — was the fee+hedge edge robust enough on its own, or did it need a reward income stream to be GO?

## D3 answer

D3 finds a **63.52% AERO reward APR** (DefiLlama) for the 0xb2cc pool. Adding this to D2:

- D2 best cell net: $6.83/day
- D3 best cell net (with observed reward): $8.32/day
- Improvement: 22% (modest, but the reward layer is real and observable)

D3 is also more robust because it tests 5 reward scenarios (0%, 15%, 31.76%, 63.52% observed, 100%) and finds the cell is GO under all of them — even at 0% reward, the D2 base is enough.

## D2 cells that D3 supersedes

| D2 best cell | D2 net | D3 net (same cell, observed reward) | D3 best cell | D3 net |
|---|---|---|---|---|
| 0xb2cc $1000 ±2% 24h hedge=0.75 | $6.83 | $8.32 | 0xb2cc $1000 ±2% 24h hedge=0.75 funding=median reward=63.52% | $8.32 |

D3's best cell is identical to D2's best cell — the reward just thickens the edge. This confirms D2's cell selection was correct.

## D2's PAUSED status

D2 said: "GO (plan only) — model is robust; next stage is D3 reward APR."

D3 says: "GO (plan only) — D2 was right; reward APR is observed and adds another 22% to the edge."

The status upgrade is the same. D2 already passed all GO criteria; D3 strengthens the case.

## What's still uncertain after D3

- DefiLlama's 63.52% APR is a 30-day rolling average. The realized 24h reward could be ±50% of that. **A 7d paper run is needed to confirm** (D4).
- The auto-exit wiring is still missing (P0 from R3). The next engineering stage after D4 would be the auto-exit Go code.
- The dynamic hedge strategy (using current LP delta) gave 0 positives in D2; D3 inherits the same issue. The static 0.75 hedge is the recommended approach.
- The reward claim gas ($0.10 per claim, 1 per 24h) is a placeholder; the actual cost would be 1-2 cycles per claim.

These are the residual uncertainties that D4 (paper validation) and a future engineering stage would address.
