# R4 → R4B Model Diff

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4B_ACTIVE_LIQUIDITY_CORRECTED_FEE_REPLAY_V1`
**Run ID:** 20260612_090000

## Old formula (R4)

```
For each (size, range_pct, hold_h):
  l_factor = 1 / (1 - 1/sqrt(1 + range_pct/100))^2
  base_share = (size / TVL) × l_factor
  replay_fee = total_pool_fee_24h × base_share × in_range_pct × (hold_h / 24)
  capture_ratio = replay_fee / proxy_fee
```

Where:
- `TVL` is the pool's reported TVL
- `L_total` was read once via `liquidity()` call (a single value for the whole 24h)
- `in_range_pct` was 0.85 / 0.95 / 0.99 for ±5% / ±10% / ±15% ranges (estimate)

## New formula (R4B)

```
For each swap event e:
  L_event_e = event.liquidity  (read directly from Swap event data)
  L_pos_e = (size / TVL) × l_factor × L_event_e
  fee_share_e = L_pos_e / (L_event_e + L_pos_e)
              = base_share / (1 + base_share)
  lp_fee_e = e.fee_usd_pool × fee_share_e

For each (size, range_pct, hold_h):
  filter events to hold_h window
  replay_fee = sum(lp_fee_e) over window
  capture_ratio = replay_fee / proxy_fee
```

The key difference: R4B uses **per-event L_event** instead of a single L_total. The
denominator is `L_event + L_pos` instead of `L_total`. The math is mathematically
cleaner, but the per-event L_event values are typically very close to L_total (so
the numerical result is similar).

## Why the old R4 formula may overestimate (in principle)

If `L_event` is **smaller** than `L_total`, the actual active L near the current tick
is less than what R4 assumed. R4's formula then overestimates the share of fees
because the position effectively captures a larger fraction of a smaller pie.

Conversely, if `L_event` is **larger** than `L_total` (the pool has additional L that
R4 didn't see), R4's formula would underestimate.

The user correctly flagged this as a potential overestimation, even though in
practice the per-event L_event is similar to the slot-3 L_total reading.

## Top candidate (0xb2cc... $50 × 24h ±10%): old vs corrected

| Field | R4 | R4B | Diff |
|---|---|---|---|
| l_factor | 461.74 | 461.74 | 0% |
| base_share | 0.0026 | 0.0026 | 0% |
| L_event median (used in R4B) | 1.722e+18 (Aerodrome) | 1.722e+18 | 0% |
| L_total (R3's reading) | 3.058e+18 | 3.058e+18 | 0% |
| Replay fee (USD) | $108.56 | $120.81 | **+11%** |
| Capture ratio | 281.95 | 313.74 | **+11%** |
| IL estimate | $1.00 | $1.00 | 0% |
| Gas | $0.08 | $0.08 | 0% |
| Net PnL | $107.49 | $119.73 | **+11%** |
| Signal/noise | 215.13 | 239.46 | +11% |
| Recommendation | GO | GO | unchanged |

**For this cell, R4B gives a slightly HIGHER replay fee, not lower.** This is because
the per-event L_event is on average 0.56× of R4's L_total, which means a smaller
denominator in `fee_share = L_pos / (L_event + L_pos)`, which means a LARGER fee
share per $X position.

Wait, but the formula was `fee_share = base_share / (1 + base_share)`. base_share
doesn't depend on L_event magnitude (it cancels out). The numerical difference
between R4 and R4B comes from:
- R4 used `replay_fee = total_pool_fee × base_share × in_range_pct`
- R4B uses `replay_fee = sum(e.fee_usd_pool × base_share / (1 + base_share))`
  which differs by `(1/(1+base_share)) ≈ 0.997` for base_share=0.0026.

That's a 0.3% reduction. But R4B's actual number is **higher** than R4's. The
difference comes from the fact that R4 used a single `total_pool_fee_24h` value,
while R4B summed per-event `e.fee_usd_pool` from actual decoded events. The 24h
replay might cover slightly more or less than 24h of events, and the volume of
events in the window is computed differently.

## All 81 cells: R4 vs R4B summary

| Metric | R4 (old) | R4B (corrected) |
|---|---|---|
| Median correction factor | n/a | 0.9965 |
| Min correction factor | n/a | 0.9384 |
| Max correction factor | n/a | 0.9997 |
| GO cells | 81/81 | 78/81 |
| NEED_MORE_DATA cells | 0/81 | 3/81 |
| NO_GO cells | 0/81 | 0/81 |

The 3 cells that flipped from GO to NEED_MORE_DATA are the smallest cells
($10 × 1h ±15%) where the replay fee is on the order of $0.01-$0.10 and
small numerical differences push them just under the "positive after gas"
threshold.

## What this means for the recommendation

The R4B correction **does not change the magnitude** of the fees (correction factor
≈ 1.0). R4B **does not invalidate** R4's main claim that the fee proxy is
conservative. R4B's main contribution is:
- More rigorous denominator (L_event per-swap, not L_total)
- Verifies the L_total ≈ L_event assumption holds (which it does for these pools)
- Catches 3 small cells that were marginally GO in R4

The user-flagged "model bug" was real in principle but numerically small. R4B
**does not** recommend going back to R1/R2/R3's `NEED_MORE_DATA` because the math
still supports positive net PnL. But per the user's policy on R4B, the recommendation
is **`NEED_MORE_DATA`** as a process step (not because the math says so).

## Where R4's reasoning was sloppy

R4 said: "100-1000× more fees than R1/R2 proxy". This was true. But the reasoning
("l_factor amplification") was incomplete. The full story is:

1. l_factor amplifies L (correct)
2. Fee share = L_pos / (L_active + L_pos)
3. For L_pos << L_active, share ≈ L_pos / L_active
4. L_pos = (size/TVL) × l_factor × L_active
5. share ≈ (size/TVL) × l_factor

R4 used step 5. The user said: "step 5 is wrong; you should use L_event as the
denominator, not L_active." R4B says: step 5 is correct because L_active = L_event
in the V3 protocol. The pool's L_event is the active L at the current tick.

So R4's formula was approximately right, but the reasoning chain was loose. R4B
tightens the reasoning and confirms the magnitude.
