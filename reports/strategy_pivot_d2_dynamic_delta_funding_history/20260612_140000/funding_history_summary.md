# D2 Funding History Summary

## Source

| Source | Endpoint | Auth | Records | Days |
|---|---|---|---|---|
| Binance | `https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT` | none | 269 | 89.3 |

Hyperliquid and OKX were not pulled because Binance's USD-margined perp is the most liquid ETH perp and the 90d history is sufficient for regime analysis. Hyperliquid's funding history is not exposed via a simple paginated endpoint (would require multiple `candleSnapshot` or `userFills` calls; not strictly needed for regime label).

## Statistics

- **Mean APR**: +0.49%
- **Median APR**: +0.83%
- **Stddev**: 6.17%
- **5th percentile**: -9.02%
- **50th percentile (median)**: +0.83%
- **95th percentile**: +9.59%

## Time-in-regime

- **% time shorts pay (rate < 0)**: 43.5%
- **% time shorts receive (rate > 0)**: 56.5%
- **% time at zero**: 0.0%

## Streak analysis

- **Longest adverse streak (consecutive 8h periods where shorts paid)**: 16 periods = **128 hours** = 5.3 days

## Current funding

- **Current APR** (last record): -2.6324%
- **Current percentile rank** in the 90d history: 30%

## Regime label

**NEUTRAL**

## Interpretation

- Mean APR is +0.49% (positives mean shorts RECEIVE funding).
- The 90d average gives the realistic funding cost for a SHORT hedge held over a 24h period.
- The longest adverse streak tells us the worst-case run of unfavorable funding that a SHORT position would have to absorb.
- Current funding percentile tells us whether the current regime is at the friendly or unfriendly end of the historical range.

The D2 dynamic-delta replay uses the median APR (+0.83%) as the "expected" funding and the 5th/95th percentiles (-9.02% / +9.59%) as the stress test range. If the replay is positive at median but negative at 5th percentile, the strategy is funding-dependent and should be PAUSED or PIVOTED.
