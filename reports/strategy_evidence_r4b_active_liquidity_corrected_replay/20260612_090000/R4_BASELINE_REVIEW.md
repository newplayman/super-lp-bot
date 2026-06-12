# R4 Baseline Review — R4B

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4B_ACTIVE_LIQUIDITY_CORRECTED_FEE_REPLAY_V1`
**Run ID:** 20260612_090000
**R4 source:** `reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000/`

## R4 final_recommendation (carried into R4B)

**`GO_TINY_LIVE_PLAN_ONLY`**

Top cell: `0xb2cc... $50 × 24h ±10%` with replay fee $108.56 (R4 model) and net
$107.49 after $0.08 gas and $1 IL estimate.

## R4's key claims (the ones R4B must verify)

1. **R1/R2 fee proxy is conservative by 100-1000×** for tight-range positions.
   - R4's reasoning: the R1/R2 model assumes full-range LP, but real concentrated LPs
     earn 100-1700× more per dollar due to `l_factor` amplification
     (`1 / (1 - 1/sqrt(1+R))^2` ≈ 1700 for ±5% range).
   - R4B's check: the 100-1700× l_factor is correct in the formula, but R4's
     `fee_share = (size/TVL) × l_factor` formula has a denominator issue.

2. **The 24h replay volumes are 7-53% lower than R2's reported volumes.**
   - R4's evidence: 28,483/80,378/6,819 Swap events decoded per pool, totaling 115,680.
   - R4B: agrees. R4B's replay uses the same 115,680 events.

3. **Top cell expected net: $107.49 over 24h for $50 size, ±10% range.**
   - R4B: corrected to $120.81 (+11% from R4). Slightly higher because the per-event
     L_event values are slightly different from the R4 single-L_total reading.

## What the user said about R4 (carried into R4B)

> R4 uses `position_size / TVL × l_factor` to estimate LP fee share, but the correct
> CLMM denominator is active liquidity near tick, not pool TVL.
> R4 didn't use the Swap event's `liquidity` as the active liquidity denominator.
> R4 script only checks if report files exist; can't reproduce the replay.
> R4 must be downgraded to `DATA_CAPTURE_PASS / FEE_MODEL_REJECTED_PENDING_R4B`.

**R4B's job**: use the Swap event's `liquidity` field as the per-event active
liquidity denominator, recompute the 81-cell matrix, and re-decide.

## R4B's three-part deliverable

1. **Liquidity scaling sanity check**: per-pool distribution of L_event values; verify
   L_event median is in the expected range; check for share > 5% anomalies; verify the
   implied daily APR is plausible.

2. **Corrected replay matrix**: 81 cells, each with the per-event corrected fee share.

3. **Model diff**: side-by-side R4 vs R4B for the top cell, with explanation of why
   the correction factor is what it is.

## R4B's headline result

| Pool | L_event median | L_total (R3 reading) | Ratio L_event/L_total |
|---|---|---|---|
| 0xb2cc... (Aerodrome Slipstream) | 1.722e+18 | 3.058e+18 | **0.56** |
| 0x72ab... (PancakeSwap V3 0.01%) | 5.824e+17 | 6.013e+17 | **0.97** |
| 0xb775... (PancakeSwap V3 0.05%) | 1.377e+17 | 1.375e+17 | **1.00** |

The Aerodrome Slipstream pool has more L variance (the L_total reading was at a peak;
the median is 56% of the peak). The PancakeSwap V3 pools are stable.

**For the fee share formula, this means**:
- R4 used L_total as denominator. The corrected formula uses L_event per-swap.
- For PancakeSwap V3 pools, the correction is tiny (L_event ≈ L_total).
- For Aerodrome Slipstream, the correction is ~0.56× (lower L_event = higher
  fee_share per $X position = more fees per dollar).

Wait — that's the opposite of what the user expected. **Lower L_event means HIGHER
fee_share** (since `fee_share = L_pos / (L_event + L_pos)`, smaller denominator
gives larger share). So R4 was actually **underestimating** the fee for 0xb2cc by
~1.7× (since 1/0.56 ≈ 1.8).

The R4B correction therefore makes the Aerodrome Slipstream fee capture **even
higher** than R4 said, not lower. This is the **opposite** of what the user feared.

## Why R4B recommendation is still `NEED_MORE_DATA`

Even though the corrected math is stronger (Aerodrome Slipstream is even more
profitable than R4 said), R4B follows the user's policy:
- The R4 formula was not rigorous.
- R4B's corrected formula needs verification (e.g., shadow probe, more samples).
- The user explicitly disallowed `GO_TINY_LIVE_PLAN_ONLY` as the R4B verdict.

R4B recommends `NEED_MORE_DATA` with a clear next stage: a 7d shadow probe or
another verification step before the recommendation can be upgraded to GO.
