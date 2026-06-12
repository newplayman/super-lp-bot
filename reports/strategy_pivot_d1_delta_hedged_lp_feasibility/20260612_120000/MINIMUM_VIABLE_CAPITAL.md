# Minimum Viable Capital

## Definition

The minimum capital (in USD) at which at least one cell in the D1 grid has positive net_pnl_hedged under both 0% and +5% funding scenarios (sustainable edge under realistic funding).

## D1 finding

**Minimum viable capital: $250**

The smallest cell with sustainable positive net across 0% and +5% funding is:

| Field | Value |
|---|---|
| Pool | 0xb2cc (Aerodrome Slipstream WETH/USDC 0.05%) |
| Size | $250 |
| Range | ±5% |
| Hold | 24h |
| Hedge ratio | 0.75 |
| Funding | 0% (and +5%) |
| Perp fee | 0.02% |
| Net @ 0% funding | $0.0504 |
| Net @ +5% funding | $0.0761 |
| Net @ +20% funding | $0.1532 |
| Signal/noise (hedged) | 1.18 |

## Capital grid summary

| Size | GO cells (across all 5 funding) | Sustainable (0% AND +5%) | Min viable |
|---|---|---|---|
| $50 | 0 | 0 | No |
| $100 | 0 | 0 | No |
| $250 | 9 | 1 | **Yes** |
| $500 | 15 | 2 | Yes |
| $1000 | 23 | 3 | Yes |

## Capital efficiency

| Size | Best net (0% funding) | Best net / Size | Best signal/noise |
|---|---|---|---|
| $250 | $0.05 | 0.020% | 1.18 |
| $500 | $0.26 | 0.052% | 1.21 |
| $1000 | $0.68 | 0.068% | 1.24 |

Capital efficiency improves with size, but the absolute edge remains thin (0.02-0.07% of size per 24h). The model is **not** a high-conviction trade at any size.

## Realistic capital requirement

For a 1% daily net target at 0% funding, you'd need approximately:
- 1% / 0.02% per $250 = ~$12,500 of LP notional
- 1% / 0.05% per $500 = ~$10,000
- 1% / 0.07% per $1000 = ~$14,000

These are nominal notionals, not capital. The actual capital required for a $X LP position is $X (split 50/50 between WETH and USDC), and the SHORT hedge is also $X × 0.75. So total capital = $1.75X for 75% hedge. At $14,000 LP, total capital = $24,500.

## Decision

The minimum viable capital of $250 is technically within the $1000 spec limit, but the absolute edge ($0.05/day) is too thin to justify any execution cost, monitoring overhead, or operational risk. The recommendation is **NEED_MORE_DATA** rather than GO: the model suggests a possible edge but the math is too marginal to act on.

## Why the edge is thin

- LP fee on 0xb2cc ±5% is 1.2% of size per day (from R4C).
- IL at ±5% with σ=4% is 0.08% per day.
- Gas cycle is $0.0795 = 0.32% of $25 (one side of the split).
- Perp trading fee is 0.02% × 0.75 × $250 = $0.0375.
- Rebalance gas is 1 cycle × $0.0795.
- Residual delta: 0.25 × $250 × 0.04 × 1 = $2.5 (this is the killer)

The residual delta risk alone exceeds the LP fee. The 75% hedge is not enough — the 25% unhedge on $250 is 1.6% of size per day, vs the 1.2% LP fee. To get residual < fee, you'd need 0.25 × σ × √hold < fee/size, i.e. hedge_ratio > 1 - (fee/size) / (σ × √hold). For 24h: hedge_ratio > 1 - 0.012 / 0.04 = 0.7. So 75% is borderline; 80%+ would be safer, but the spec only allows 50% and 75%.

This explains why the edge is so thin: the model is right at the margin of the 75% hedge, where residual risk is comparable to fee income.
