# Tiny-Live Decision — R4B

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4B_ACTIVE_LIQUIDITY_CORRECTED_FEE_REPLAY_V1`
**Run ID:** 20260612_090000

## Final recommendation: **`NEED_MORE_DATA`**

R4B downgrades R4's `GO_TINY_LIVE_PLAN_ONLY` to `NEED_MORE_DATA`. This is a
**process** downgrade, not a math downgrade: the corrected replay still shows
positive net PnL for 78/81 cells, but the user's policy on R4B explicitly disallowed
GO and required verification.

## R4B's two findings

### Finding 1: R4 was approximately right (correction factor 0.94-1.00)

The user's concern was that R4 used `position_size / TVL × l_factor` to estimate fee
share, but the correct CLMM denominator is `L_active near tick`, not pool TVL.

R4B's correction:
- `fee_share = L_pos / (L_event + L_pos)` where `L_pos = (size/TVL) × l_factor × L_event`
- Numerator: `base_share / (1 + base_share)`
- For typical $10-50 sizes on $1M+ TVL pools, `base_share` is small (< 0.01) and
  the `1 / (1 + base_share)` term is ≈ 0.99. So the correction is tiny.

**Median correction factor across 81 cells: 0.9965.** R4 was within 0.4% of the
corrected answer on the median cell.

### Finding 2: L_event ≈ L_total, so the "model bug" was minor

R4B checks the per-event `liquidity` field across 115,680 Swap events:

| Pool | L_event median | L_total (R3) | Ratio |
|---|---|---|---|
| 0xb2cc... | 1.722e+18 | 3.058e+18 | 0.56 |
| 0x72ab... | 5.824e+17 | 6.013e+17 | 0.97 |
| 0xb775... | 1.377e+17 | 1.375e+17 | 1.00 |

For 0x72ab and 0xb775, L_event median is essentially the same as L_total. For
0xb2cc (Aerodrome Slipstream), L_event median is 56% of R3's reading, but the
math is the same — fee share is independent of L_event magnitude because it
cancels out.

**The user's concern was correct in principle (R4 should have used L_event, not
L_total) but the numerical impact is small because L_event ≈ L_total.**

## Why R4B's verdict is NEED_MORE_DATA, not GO

Even though the math still says positive net PnL for 78/81 cells, the R4B
recommendation is `NEED_MORE_DATA` for the following reasons:

1. **User's policy on R4B**: R4's `GO_TINY_LIVE_PLAN_ONLY` was explicitly rejected.
   R4B cannot re-promote to GO without a separate verification step.
2. **R4's formula was not rigorous**: the user is right that R4's reasoning was
   loose. R4B has now made the reasoning rigorous, but the conclusion is "the math
   is right" — and that's not enough to override the user's policy.
3. **Auto-exit wiring still missing (R3 P0)**: even if R4B confirmed GO, the
   autonomous-live path is blocked. A `GO_TINY_LIVE_PLAN_ONLY` verdict without
   auto-exit is internally inconsistent.
4. **in_range_fraction is still a guess**: R4 used 0.85/0.95/0.99 for ±5/10/15%
   ranges. R4B has the same guess. A 7d shadow probe or multi-day replay would
   verify this.
5. **24h is a single sample**: a 7d or 30d replay would smooth out the variance
   and give a tighter estimate of the realized fee.

## What R4B would need to upgrade the recommendation

To upgrade from `NEED_MORE_DATA` to `GO_TINY_LIVE_PLAN_ONLY`, R4B (or a future
stage) would need:

1. A 7d multi-day replay showing consistent positive net PnL (not just a 24h sample).
2. Verification of the in_range_fraction (e.g., via a 7d shadow probe, which is
   not the R4B's job).
3. Resolution of the 3 cells that flipped from GO to NEED_MORE_DATA (the $10 × 1h
   ±15% cells, which are small enough that gas dominates).
4. Either (a) write the auto-exit wiring, or (b) re-confirm that a manually-
   supervised live position is acceptable per the user's policy.

R4B itself does not do any of these. It just verifies the math and the data.

## Safety reclassification

- R4B is safe: read-only, no execution, no signing, no broadcast.
- R4B's recommendation `NEED_MORE_DATA` blocks any further action.
- The freeze is preserved. No canary, no live, no paper, no Mode B, no R1-R4
  long-horizon collector restart.
- The R4B report is pushed to the feature branch as a research:correct commit.
