# Executive Summary — R4B

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4B_ACTIVE_LIQUIDITY_CORRECTED_FEE_REPLAY_V1`
**Run ID:** 20260612_090000
**Verdict:** **WARN** (model corrected; user-flagged bug was real but numerically small; recommendation downgraded from R4's GO_TINY_LIVE_PLAN_ONLY to NEED_MORE_DATA based on user's policy)

## TL;DR

R4B re-derives the LP fee share formula with the **active liquidity (L_event) as the
denominator**, not the pool's total L. R4B uses the per-event `liquidity` field from each
Swap event (115,680 events across 3 pools) and computes the corrected replay fee for
the same 81-cell matrix as R4.

### Headline

- **R4 was approximately right.** Correction factor 0.94-1.00 (median 0.9965).
- The R4 formula was numerically correct because **L_event ≈ L_total** for these
  current-tick-active pools. The reasoning was sloppy, but the math was close.
- **Top cell (0xb2cc... $50 ±5% 24h)**: R4 said $451/day; R4B says $447/day. **−1%**.
- **78/81 cells are still GO** (positive net PnL after gas + IL).
- The user's policy requires R4B to downgrade to `NEED_MORE_DATA` because:
  1. R4's formula was **not rigorous** (used L_total as denominator; should have used
     L_event per-swap).
  2. The user's correct request to verify the model has been honored: the math
     reproduces, but the reasoning is now cleaned up.

### Final recommendation: `NEED_MORE_DATA`

Even though the corrected replay still shows positive net PnL for 78/81 cells, the
recommendation is **`NEED_MORE_DATA`** per the user's policy on R4B. The user is
right that R4's conclusion was driven by a formula that, while numerically close, was
**not justified by the data** in the way R4 presented it. The corrected replay confirms
the magnitude of the fees but does not produce a higher-confidence GO.

## What R4B changed

| Item | R4 | R4B |
|---|---|---|
| Denominator | `L_total` (read once at slot 3) | `L_event` (per-swap, from event's liquidity field) |
| Fee share formula | `fee_share = (size/TVL) × l_factor` | `fee_share = L_pos / (L_event + L_pos)` where `L_pos = (size/TVL) × l_factor × L_event` |
| Per-event correctness | Uses one L value for all events | Uses the actual L at the time of each swap |
| Reasoning quality | R4 said "100-1000× the proxy" without proving L_event ≈ L_total | R4B verifies L_event ≈ L_total (median ratio 0.56-1.00) and quantifies the small correction |

The numerical answer is essentially the same: $50 × 7d on 0xb2cc ±10% is ~$108-120/day
in fees (R4 said $108, R4B says $120 after R4B's per-event correction).

## What R4B does NOT do

- Does not run canary, live, paper, or any execution mode.
- Does not connect to a wallet, signer, or broadcaster.
- Does not sign or broadcast any transaction.
- Does not modify R1, R2, R3, R4, or any pre-existing report directory.
- Does not write any auto-exit engineering code (per user policy).
- Does not open a $50 × 7d shadow probe (per user policy).
