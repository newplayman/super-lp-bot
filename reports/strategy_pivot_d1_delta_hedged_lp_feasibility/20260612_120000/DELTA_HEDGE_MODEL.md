# Delta-Hedge Model

## Model overview

Static, deterministic, single-period model. Computes expected net PnL for a CLMM LP position hedged with a SHORT ETH perp position, across a 7-dimensional grid.

## Inputs

- **LP fee per dollar per day** (from R4C):
  - 0xb2cc ±5%: 1.20% of size per day (extrapolated from R4C ±5% = $0.5994 for $50/day, scale-invariant)
  - 0x72ab ±5%: TBD (loaded from R4C matrix)
  - 0xb775 ±5%: TBD
  - Other ranges scaled by IN_RANGE_FRAC × √(24/hold) for holds > 24h
- **Hedge funding**: spec scenario table -20% to +20% APR in 5 steps. Sanity-checked against live Hyperliquid + Binance data (-8% APR currently).
- **Hedge trading fee**: spec scenario 0.02%, 0.05%, 0.10%.
- **ETH volatility**: σ_daily = 4% (76% annualized). Conservative for ETH (60-80% annualized range typical).
- **Hedge ratio**: 0.5 or 0.75 of notional (per spec).
- **IL/LVR formula**:
  - LVR_daily = 0.5 × σ_daily²
  - Range amplification factor: 1x for ±10% or wider, up to ~2x for ±1% with cap at 5%/day
- **Rebalance cost**: 1 gas cycle per 24h of holding ceiling (assumes static range; realistic rebalance count would be higher for very tight ranges).
- **Gas cycle**: $0.0795 (R2 typical 0.05 gwei anchor).
- **Hold horizons**: 1h, 6h, 24h, 72h, 7d. Fee scales linearly with hold_days (no compounding, no decay model).
- **Size grid**: $50, $100, $250, $500, $1000.
- **Range grid**: ±1%, ±2%, ±5%, ±10%, ±15%.

## Per-cell formula

```
lp_fee = fee_per_dollar_per_day × size × hold_days
il = size × lvr_daily × range_amplification × hold_days
hedge_notional = size × hedge_ratio
funding_cost = -hedge_notional × (funding_apr / 100) × (hold_h / 8760)  # negative = income
hedge_trading_fee = hedge_notional × perp_fee  # entry only
rebalance_cost = gas_cycle × ceil(hold_h / 24)
residual_delta = (1 - hedge_ratio) × size × σ_daily × √(hold_days)
gas = gas_cycle

net_pnl_hedged = lp_fee - il - funding_cost - hedge_trading_fee - gas - rebalance_cost - residual_delta
net_pnl_unhedged = lp_fee - il - gas

signal_hedged = max(lp_fee - il, 1e-9)
noise_hedged = max(il × 0.5 + residual × 0.5, 1e-6)
signal_noise_hedged = signal_hedged / noise_hedged
```

## Recommendation thresholds

- **GO**: net_hedged > 0 AND signal_noise_hedged > 1.0 AND size <= $1000
- **NEED_MORE_DATA**: net_hedged > -0.1 (marginal)
- **NO_GO**: net_hedged <= -0.1 (clearly negative)

## Funding cost sign convention

Funding is "long pays short when rate > 0". For a SHORT hedge:
- If funding_apr > 0 (longs pay): shorts RECEIVE → funding_cost is negative (income)
- If funding_apr < 0 (shorts pay): shorts PAY → funding_cost is positive (cost)

The spec's scenarios -20%, -5%, 0%, +5%, +20% span the realistic range. Current observed funding of -8% APR (shorts pay) is between the 0% and -5% scenarios. The +20% scenario is a tail-favorable case for the SHORT thesis.

## Rebalance cost assumption

A static range is degenerate for tight ranges. R4C's analysis showed 100% in-range for ±5/10/15% over 24h on these pools, which is realistic for ETH/USDC (24h tick stddev is < 1% price). For ±1% and ±2% over 24h, 70% / 95% in-range fractions are assumed. For 72h and 7d, a √(24/hold) decay factor is applied. The rebalance cost is 1 gas cycle per 24h ceiling — in practice a ±1% range would rebalance 2-3x per 24h, so the model understates rebalance cost for tight ranges over long holds.

## Residual delta risk

`residual = (1 - hedge_ratio) × size × σ_daily × √(hold_days)`

This is the 1-σ move on the unhedge-portion over the holding window. For 0.75 hedge over 24h on $1000: 0.25 × 1000 × 0.04 × 1 = $10. For 0.75 hedge over 7d: 0.25 × 1000 × 0.04 × √7 = $26.5. Significant relative to the ~$0.5-1.0 net PnL.

## LVR/IL note

The model uses σ_daily = 4% (annualized ~76%). This is conservative for ETH (recent realized vol is 50-70% annualized). Higher σ = higher LVR = lower net PnL. Lower σ would make the model more favorable.

## Limitations

- **Static position** — doesn't model the auto-rebalance case where the LP re-centers as tick moves.
- **Linear fee extrapolation** for 72h / 7d — actual fees may decay if volume drops or the position goes out of range.
- **Single LVR formula** — doesn't account for the specific CLMM "concentrated IL" (which can be larger than LVR for very tight ranges).
- **No slippage / market impact** for the SHORT position — assumes market orders fill at the mark.
- **No funding rate changes** during the hold — assumes a constant rate.
- **No exit cost** — exit is assumed free except the rebalance gas.

These limitations bias the model toward more favorable net PnL. The actual live EV is likely lower than the model's projections.
