# R4C Baseline Review

D1 builds on R4C's findings. R4C's verdict was FAIL / MODEL_BUG_FOUND:
- All 81 cells (3 pools × 3 sizes × 3 ranges × 3 holds) had negative net PnL under proper CLMM math.
- R4B's "active liquidity correction" was mathematically a no-op (L_event cancels in the fee_share formula).
- R4B's fee was 125-833x too high; R4C's correct fee is 0.0001-0.0008% per swap.

D1 uses R4C's fee_per_dollar_per_day values as the LP fee input. R4C's IL formula was reused but corrected: R4C's `il = size × σ² / R² × 0.5 × hold_days` formula overstates IL for tight ranges by 100-1000x. D1 uses a realistic LVR-based IL formula:

```
LVR_daily = 0.5 × σ_daily²
il_daily = LVR_daily × range_amplification
range_amplification:
  R >= 10% (loose):  1.0
  R in [2%, 10%]:    1.0 + (0.10 - R) × 5
  R < 2% (tight):    1.0 + 0.4 + (0.02 - R) × 50, capped at 100
  absolute cap: 5% per day
```

For ETH with σ_daily = 4%:
- ±5% range: il_daily ≈ 0.08% × 1.0 = 0.08% of size per day
- ±10% range: 0.08% × 1.0 = 0.08% per day
- ±15% range: 0.08% × 1.0 = 0.08% per day
- ±2% range: 0.08% × 1.4 = 0.11% per day
- ±1% range: 0.08% × 1.9 = 0.15% per day

At $50 size: $0.04-$0.08 per day. Reasonable for LVR.

## R4C cells that informed D1

| Pool | R4C fee/size/day (24h) | R4C cell used in D1 |
|---|---|---|
| 0xb2cc | 0.62% (range 10%) | Base; ±5% extrapolated to 1.2% |
| 0x72ab | TBD | Base |
| 0xb775 | TBD | Base |

## R4C IL formula vs D1 IL formula

| Position | R4C IL/day (σ=2%) | D1 IL/day (σ=4%, LVR-based) |
|---|---|---|
| $50 ±1% | $200 | $0.075 |
| $50 ±5% | $8 | $0.04 |
| $50 ±10% | $2 | $0.04 |
| $50 ±15% | $0.89 | $0.04 |

The R4C formula's `(σ/100)² / R²` produces absurd values for tight ranges because:
1. σ is the per-period vol, but R is a price ratio. The ratio σ²/R² has units of time⁻¹ and grows as 1/R².
2. The formula's "0.5" is from a different closed-form derivation (LP loss for a full-range LP), not a tight-range concentrated LP.

D1's LVR-based formula is appropriate for tight-range CLMM LPs.

## R4C's other findings that D1 inherits

- **L_position math is correct** — D1 uses R4C's `fee_per_dollar_per_day` values directly.
- **Tick decoder is corrected** — D1 doesn't decode ticks; it uses R4C's per-event in-range counts.
- **Pool set** — 0xb2cc, 0x72ab, 0xb775 (top 3 by volume from R1).
- **Fee tier** — 0.05% (0xb2cc, 0xb775) and 0.01% (0x72ab) per pool metadata.

## What D1 adds beyond R4C

- **Hedge funding** from public perp endpoints (HL, Binance; OKX blocked).
- **Hedge trading fee** scenarios (0.02% to 0.10%).
- **Rebalance gas** (1 gas cycle per 24h ceiling).
- **Residual delta risk** = (1 - hedge_ratio) × size × σ_window.
- **Per-cell signal/noise** for hedged and unhedged cases.
- **Wider grid**: 5 sizes ($50-$1000), 5 ranges (±1% to ±15%), 5 horizons (1h to 7d).

D1's matrix has 11,250 cells (3 pools × 5 × 5 × 5 × 2 × 5 × 3) — 139x more cells than R4C's 81.
