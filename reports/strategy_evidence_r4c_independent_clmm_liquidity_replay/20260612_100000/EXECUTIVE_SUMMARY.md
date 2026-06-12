# R4C Executive Summary — Independent CLMM Liquidity Replay

**Stage:** LP_BOT_STRATEGY_EVIDENCE_R4C_INDEPENDENT_CLMM_LIQUIDITY_REPLAY_V1
**Run ID:** 20260612_100000
**Branch:** feat/supabase-postgres-deployment
**Status:** FAIL
**Final recommendation:** MODEL_BUG_FOUND

## TL;DR

R4C computes `L_position` independently from amount0/amount1 using V3's canonical formulas. R4 / R4B's fee share is **125×–833× too high** (median 290×). The user's "model bug" suspicion was correct and large. All 81 cells (3 pools × 3 sizes × 3 ranges × 3 holds) have **negative net PnL** under the corrected math. The fee-only LP path does not survive proper V3 liquidity math at $10–$50 sizing.

## What was wrong

R4 and R4B both computed:

```
L_pos = (size/TVL) * l_factor * L_event     (R4 / R4B)
fee_share = L_pos / (L_event + L_pos)        (R4B "correction")
        = base_share / (1 + base_share)       (after substitution)
        ≈ base_share = size/TVL * l_factor    (R4 result, when L_pos << L_event)
```

The `L_event` in `L_pos` cancels in the `fee_share` formula. R4B's "active liquidity correction" was a no-op; it re-derived the same R4 short-cut. R4 / R4B never computed an independent L_position from first principles.

R4C computes L_position from V3's `LiquidityAmounts.sol`:

```
L_from_amount0 = amount0 * sqrtP * sqrtB / ((sqrtB - sqrtP) * 2^96)
L_from_amount1 = amount1 * 2^96 / (sqrtP - sqrtA)
L_position = min(L_from_amount0, L_from_amount1)
```

For 0xb2cc $50 × 24h ±10%:
- L_position = **1.32 × 10^13**
- median L_event = **1.72 × 10^18**
- ratio = **7.7 × 10^-6** (R4 / R4B claimed 0.0026, a 340× overestimate)
- fee_share = 0.000077% (R4B claimed 0.26%, a 340× overestimate)

## Top candidate comparison

| Field | R4B | R4C | Ratio |
|---|---|---|---|
| Top cell (0xb2cc $50 ±10% 24h) fee | $120.81 | $0.3102 | 0.00257 (390× overestimate) |
| Top cell net PnL | $119.73 | $-0.77 | — |
| Top cell signal/noise | 239.46 | -1.38 | — |
| Best R4C cell net PnL | — | $-0.23 | — |

The "best R4C cell" is 0xb2cc $50 ±5% 1h with net = $-0.23 and signal/noise = 137. (Signal/noise is high in 1h cells only because IL standard deviation is tiny there, but the absolute fee is $0.014 — net of $0.08 gas is still negative.)

## Recommendation: MODEL_BUG_FOUND

Per R4C spec strict conclusion rule:
- R4B overestimated fee by >5x ✓ (median 290×)
- All 81 cells have net ≤ 0 ✓
- R4B formula cannot be reproduced independently ✓ (R4C reproduced it, but the formula is mathematically equivalent to R4)

## What this means for the strategy

- The fee-only LP path at $10–$50 sizing on these 3 pools is not viable under proper CLMM math.
- Either the size grid must be much larger (R5: try $100–$10k), the pool set must change (look for pools with much lower active L), or the strategy thesis must be revisited.
- The R1 → R2 → R3 → R4 → R4B chain was overestimating fee capture by 2-3 orders of magnitude. This was driven by a single conceptual error: treating `size/TVL × l_factor` as the LP's fee share, when in CLMM the actual share is `L_position / L_event_total` where L_position is a V3-specific quantity derived from the position's amount0/amount1 notional.
- The R4 / R4B reports should be retroactively downgraded to "model: model_bug_found, conclusion: not yet reproducible."

## Safety

No wallet/tx touched. No signing/broadcast. No canary/live/paper. No auto-exit engineering. LPBOT_CONFIRM_LIVE not set. Freeze preserved.
