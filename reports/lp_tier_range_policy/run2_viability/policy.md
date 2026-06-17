# Tier range policy  (k=1.2)
_generated 2026-06-17T09:20:28.757543+00:00_

range = vol-sized for regime H. ER = Kaufman efficiency ratio (1=trend, 0=chop). weekly-tight gated on range-bound regime; ENTER gated on fee_cover (fees/|IL|) >= 1.

| pool | tier | σ_daily | ER | regime | ±range | fees% | IL% | net% | fee_cover | move% | action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cbBTC/WETH 0.05% | A | 2.26% | 0.22 | range-bound | ±7.2% | 0.97 | -0.79 | 2.45 | 1.22 | 4.54 | **ENTER** |
| WETH/USDC 0.05% | A | 3.72% | 0.15 | range-bound | ±11.8% | 1.35 | -0.83 | 3.33 | 1.61 | 5.64 | **ENTER** |
| cbBTC/USDC 0.05% | A | 1.93% | 0.03 | range-bound | ±6.1% | 2.27 | -0.01 | 1.86 | 157.47 | 0.80 | **ENTER** |
| WETH/USDC 0.3% | B | 3.81% | 0.17 | range-bound | ±12.1% | 0.54 | -0.77 | 2.49 | 0.7 | 5.44 | **AVOID_FEE<IL** |
| VIRTUAL/WETH 0.05% | B | 3.43% | 0.17 | range-bound | ±10.9% | 1.89 | -0.76 | -1.97 | 2.47 | 6.19 | **ENTER** |
| VVV/WETH 0.05% | B | 6.44% | 0.08 | range-bound | ±20.4% | 0.28 | -0.63 | 2.37 | 0.44 | 5.45 | **AVOID_FEE<IL** |

- **cbBTC/WETH 0.05%** — ENTER: fees cover IL; range-appropriate
- **WETH/USDC 0.05%** — ENTER: fees cover IL; range-appropriate
- **cbBTC/USDC 0.05%** — ENTER: fees cover IL; range-appropriate
- **WETH/USDC 0.3%** — AVOID_FEE<IL: fees cover only 0.70x of IL
- **VIRTUAL/WETH 0.05%** — ENTER: fees cover IL; range-appropriate
- **VVV/WETH 0.05%** — AVOID_FEE<IL: fees cover only 0.44x of IL
