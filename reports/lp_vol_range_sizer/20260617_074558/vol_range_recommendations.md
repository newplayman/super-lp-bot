# LP vol-range sizer  (k=1.2, base capital 10000U)
_generated 2026-06-17T07:45:58.545753+00:00_

range_pct = 100 * k * sigma_daily * sqrt(H_days). rebal/mo ~= 30/H. fee_idx = 10%/range (fee density vs +/-10% baseline).

## cbBTC / WETH 0.05% (correlated)  [A]
- window 1.5d, swaps 34258, hourly closes 37, returns 36
- **sigma_daily = 2.20%** (annualized ~42%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±7.0% | 4.29 | 1.43x |
| 14 | ±9.9% | 2.14 | 1.01x |
| 30 | ±14.5% | 1.00 | 0.69x |
| 45 | ±17.7% | 0.67 | 0.56x |
| 60 | ±20.5% | 0.50 | 0.49x |

## WETH / USDC 0.05%  [A]
- window 1.5d, swaps 38666, hourly closes 37, returns 36
- **sigma_daily = 3.45%** (annualized ~66%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±11.0% | 4.29 | 0.91x |
| 14 | ±15.5% | 2.14 | 0.65x |
| 30 | ±22.7% | 1.00 | 0.44x |
| 45 | ±27.8% | 0.67 | 0.36x |
| 60 | ±32.1% | 0.50 | 0.31x |

## cbBTC / USDC 0.05%  [A]
- window 1.5d, swaps 57408, hourly closes 37, returns 36
- **sigma_daily = 1.72%** (annualized ~33%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±5.5% | 4.29 | 1.83x |
| 14 | ±7.7% | 2.14 | 1.30x |
| 30 | ±11.3% | 1.00 | 0.89x |
| 45 | ±13.8% | 0.67 | 0.72x |
| 60 | ±16.0% | 0.50 | 0.63x |

## WETH / USDC 0.3%  [B]
- window 1.5d, swaps 8522, hourly closes 37, returns 36
- **sigma_daily = 3.42%** (annualized ~65%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±10.9% | 4.29 | 0.92x |
| 14 | ±15.4% | 2.14 | 0.65x |
| 30 | ±22.5% | 1.00 | 0.44x |
| 45 | ±27.6% | 0.67 | 0.36x |
| 60 | ±31.8% | 0.50 | 0.31x |

## VIRTUAL / WETH 0.05%  [B]
- window 1.5d, swaps 27538, hourly closes 37, returns 36
- **sigma_daily = 2.93%** (annualized ~56%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±9.3% | 4.29 | 1.07x |
| 14 | ±13.2% | 2.14 | 0.76x |
| 30 | ±19.3% | 1.00 | 0.52x |
| 45 | ±23.6% | 0.67 | 0.42x |
| 60 | ±27.3% | 0.50 | 0.37x |

## VVV / WETH 0.05%  [B]
- window 1.5d, swaps 8038, hourly closes 37, returns 36
- **sigma_daily = 6.83%** (annualized ~130%)

| H (days) | ±range | rebal/mo | fee density vs ±10% |
|---|---|---|---|
| 7 | ±21.7% | 4.29 | 0.46x |
| 14 | ±30.7% | 2.14 | 0.33x |
| 30 | ±44.9% | 1.00 | 0.22x |
| 45 | ±55.0% | 0.67 | 0.18x |
| 60 | ±63.5% | 0.50 | 0.16x |
