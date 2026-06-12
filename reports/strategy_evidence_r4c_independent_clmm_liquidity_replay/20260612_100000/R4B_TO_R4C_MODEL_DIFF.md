# R4B → R4C Model Diff

## R4B formula (claimed corrected)

For each swap event `e`:
```
base_share = (size / TVL) × l_factor
L_pos_e = base_share × L_event_e        ← pool's L, not position's L
fee_share_e = L_pos_e / (L_event_e + L_pos_e)
           = base_share × L_event_e / (L_event_e + base_share × L_event_e)
           = base_share / (1 + base_share)
           ≈ base_share                   ← L_event cancels
```

Net over window:
```
LP_fee_R4B = Σ_e [e.fee_usd × base_share / (1 + base_share)]
```

In code (R4B):
```python
base_share = (size / info["tvl_usd"]) * l_factor
for ev in window_events:
    L_event = ev["liquidity"]
    L_pos_e = base_share * L_event
    fee_share = L_pos_e / (L_event + L_pos_e)  # = base_share / (1 + base_share)
    lp_fee = ev["fee_usd_pool"] * fee_share
```

## Why R4B still depends on `size/TVL × l_factor`

R4B's "correction" was a denominator adjustment: replace `1` in the denominator with `1 + base_share`. But the L_event in `L_pos_e` cancels in the fee_share formula. R4B never computed an independent `L_position` from amount0/amount1.

The structural issue: R4B's `L_pos_e = base_share × L_event_e` says "if I had `base_share` fraction of the pool's current L, my L would be this." But that's a *virtual* L for an imagined position with that fraction of TVL. It does not match the actual V3 L of the new $X position, which is derived from the position's own amount0/amount1.

R4B's note: "R4B's corrected formula with L_event per-swap gives correction factor 0.94-1.00 (median 0.9965). R4 was within 0.4% of the corrected answer on the median cell." This is exactly what you'd expect when R4B = R4 × (1 / (1 + base_share)) and base_share is small.

## R4C formula (independent V3 math)

For each cell, compute `L_position` ONCE from the position's own amount0/amount1:
```
amount0 = (size/2) / price_human × 10^dec0
amount1 = (size/2) × 10^dec1
L_from_amount0 = amount0 × sqrtP × sqrtB / ((sqrtB - sqrtP) × 2^96)
L_from_amount1 = amount1 × 2^96 / (sqrtP - sqrtA)
L_position = min(L_from_amount0, L_from_amount1)
```

For each swap event `e`:
```
if e.tick in [tickLower, tickUpper]:
    fee_share_e = L_position / (L_event_e + L_position)
else:
    fee_share_e = 0
LP_fee_R4C = Σ_e [e.fee_usd × fee_share_e]
```

## Top candidate R4B vs R4C

| Field | R4B | R4C | Factor |
|---|---|---|---|
| Pool | 0xb2cc | 0xb2cc | — |
| Size × Range × Hold | $50 ±10% × 24h | $50 ±10% × 24h | — |
| L_position | 4.47e15 (= base_share × L_event) | 1.32e13 (from amount0/amount1) | **0.003** |
| L_position / median_L_event | 0.0026 | 7.65e-6 | **0.003** |
| median fee_share per event | 0.26% | 0.00077% | **0.003** |
| Replay fee (24h) | $120.81 | $0.3102 | **0.00257** |
| Capture ratio (R2 proxy) | 313.7× | 0.806× | 0.0026 |
| Net PnL | $119.73 | $-0.77 | — |
| Signal/noise | 239.46 | -1.38 | — |

R4B's replay fee is 390× higher than R4C's. R4B's net PnL was +$119; R4C's is $-0.77 (gas + IL exceed fee).

## Per-pool fee ratio (R4C / R4B)

| Pool | Min ratio | Median ratio | Max ratio |
|---|---|---|---|
| 0xb2cc | 0.0012 | 0.0025 | 0.0080 |
| 0x72ab | 0.0017 | 0.0036 | 0.0050 |
| 0xb775 | 0.0014 | 0.0041 | 0.0065 |
| **All** | **0.0012** | **0.0034** | **0.0080** |

R4B is 125× to 833× too high across all 81 cells. Median 290× overestimate.

## Decision change

| Stage | Recommendation | Net PnL | Basis |
|---|---|---|---|
| R4 | GO_TINY_LIVE_PLAN_ONLY | +$107.49 (top) | size/TVL × l_factor proxy |
| R4B | NEED_MORE_DATA | +$119.73 (top) | "corrected" but algebraically identical to R4 |
| **R4C** | **MODEL_BUG_FOUND** | **-$0.77 (top)** | **independent V3 L_position math** |

R4C's MODEL_BUG_FOUND verdict applies to the entire R1 → R2 → R3 → R4 → R4B recommendation chain, which was all based on the same flawed `size/TVL × l_factor` shortcut.

## Root cause

The conceptual error is treating the LP's fee share as `size/TVL × l_factor`. In CLMM, the fee share for a position with L=L_position in a pool with active L=L_active at the relevant tick is `L_position / (L_active + L_position)`, where L_position is a function of (amount0, amount1, sqrtP, sqrtA, sqrtB, decimals), not a function of pool TVL.

`size/TVL × l_factor` is a heuristic for "what fraction of TVL am I providing" scaled by a concentration factor, but it doesn't account for the fact that in V3, L scales with position size in a specific (non-linear) way, and the l_factor only tells you the ratio of L_position in a tight range to L_position in a full range, not the absolute L_position in either.

R4C replaces the heuristic with the actual V3 math and finds the heuristic was overestimating L_position by 100-1000×.
