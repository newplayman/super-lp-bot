# Terminal Near-Exit Mark Audit

- strict timing split:
  - 24h: strict_before_exit=0, exact_at_exit=14047, strict_after_exit=0
  - 6h: strict_before_exit=0, exact_at_exit=5683, strict_after_exit=0
- current summary table uses nearest_le_outcome_time as before and nearest_ge_outcome_time as after, so exact_at_exit marks appear in both columns.

| horizon | terminal rows total | before-exit mark coverage | after-exit mark coverage | abs distance p50 / sec | abs distance p90 / sec | abs distance p99 / sec | terminal_value_usd > 0 count | terminal net_pnl_pct calculable count | before <=5m | before <=15m | before <=30m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 24h | 14047 | 14047 | 14047 | 0 | 0 | 0 | 14020 | 14047 | 14047 | 14047 | 14047 |
| 6h | 5683 | 5683 | 5683 | 0 | 0 | 0 | 5656 | 5683 | 5683 | 5683 | 5683 |

## Before-Exit Mark Source Distribution

| horizon | mark_source | count | amount_usd present rate | valuation_usd present rate | net_pnl_usd present rate |
| --- | --- | ---: | ---: | ---: | ---: |
| 24h | geckoterminal | 8078 | 8078 | 8078 | 8078 |
| 24h | dexscreener | 5941 | 5941 | 5941 | 5941 |
| 24h | closed_from_last_open_mark+onchain_value+onchain_fees+zero_liquidity+onchain_npm+geckoterminal | 27 | 27 | 27 | 27 |
| 24h | closed_from_last_open_mark+onchain_value+onchain_fees+onchain_npm+geckoterminal | 1 | 1 | 1 | 1 |
| 6h | geckoterminal | 3398 | 3398 | 3398 | 3398 |
| 6h | dexscreener | 2257 | 2257 | 2257 | 2257 |
| 6h | closed_from_last_open_mark+onchain_value+onchain_fees+zero_liquidity+onchain_npm+geckoterminal | 27 | 27 | 27 | 27 |
| 6h | closed_from_last_open_mark+onchain_value+onchain_fees+onchain_npm+geckoterminal | 1 | 1 | 1 | 1 |

## Threshold Coverage and Risk

| threshold | horizon | coverage_count | closed-status count | valuation+net_pnl present count |
| --- | --- | ---: | ---: | ---: |
| 15m | 24h | 14047 | 14047 | 14047 |
| 15m | 6h | 5683 | 5683 | 5683 |
| 30m | 24h | 14047 | 14047 | 14047 |
| 30m | 6h | 5683 | 5683 | 5683 |
| 5m | 24h | 14047 | 14047 | 14047 |
| 5m | 6h | 5683 | 5683 | 5683 |
