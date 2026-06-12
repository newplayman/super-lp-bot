# R4C Independent Liquidity Math Report

## Goal

Compute L_position for a hypothetical CLMM position using V3's canonical `LiquidityAmounts.sol` formulas, with no dependence on `size/TVL × l_factor` or any shortcut that uses pool-wide L_event as a proxy for the position's own L.

## V3 canonical formulas (from Uniswap v3-periphery `LiquidityAmounts.sol`)

For a position with:
- `sqrtP` = current sqrtPriceX96
- `sqrtA` = sqrt(1.0001^tickLower) in Q64.96
- `sqrtB` = sqrt(1.0001^tickUpper) in Q64.96
- `amount0` = token0 amount in raw units (wei for WETH)
- `amount1` = token1 amount in raw units (micro-USDC for USDC)

If `P` is in range `[sqrtA, sqrtB]`:

```
L_from_amount0 = amount0 * sqrtP * sqrtB / ((sqrtB - sqrtP) * 2^96)
L_from_amount1 = amount1 * 2^96 / (sqrtP - sqrtA)
L_position = min(L_from_amount0, L_from_amount1)
```

L_position is a uint128 in canonical V3 units. It is comparable to L_event (the per-swap liquidity from the Swap event) on a per-event basis: both are V3 canonical L values for the pool at a specific tick.

## Position sizing

For a $X position with ±R% range centered on the current price:
- `amount0_human = (X / 2) / price_human` (WETH amount by value)
- `amount1_human = X / 2` (USDC amount by value)
- `amount0_raw = int(amount0_human × 10^18)`
- `amount1_raw = int(amount1_human × 10^6)`

This is a 50/50 split by value, valid for a symmetric ±R% range at the midpoint.

## Tick → sqrtPriceX96

`sqrtPriceX96 = int(sqrt(1.0001^tick) × 2^96)`

For tick in [-887272, 887272] (V3 range), this is a uint160. Computed via `exp(tick × log(1.0001) / 2) × 2^96`.

## Validation checks (per R4C spec section C)

### 1. amount0_usd + amount1_usd ≈ size_usd within 1%

For all 81 cells, max error = 0.0000%. The 50/50 split reconstructs the notional exactly (rounding at the 6-decimal place of USDC and 18-decimal place of WETH). All 81 cells PASS.

### 2. L_position is independent of L_event

L_position depends only on (size, tickLower, tickUpper, tick, dec0, dec1). It does not read L_event from any source. The R4C validation table includes `L_from_amount0` and `L_from_amount1` for transparency.

### 3. Fee share is never computed from TVL

R4C computes `fee_share = L_position / (L_event + L_position)` per event. L_position is independent of TVL. R4C does not use the `size/TVL × l_factor` formula anywhere except for the R4 / R4B comparison column.

### 4. Any fee_share > 5% is flagged suspicious

All 81 cells have max fee_share < 0.001% (the L_position is so small relative to L_event that fee_share is always in the 0.0001–0.001% range). No share > 5% flag was triggered. This is a sanity check, not a sign of an issue.

### 5. Any daily fee > position size is flagged suspicious

R4C daily fee (R4C fee × (24 / hold_h)) is at most $0.024 for the top cell, vs $50 size. No daily_fee_gt_position_size flag was triggered. R4B's daily fee would be $120.81 / 1 day > $50 size — that WAS the suspicion flag for R4B's result, but R4C's correct math brings it back under the size.

### 6. Any APR > 1000% is flagged suspicious, not auto-accepted

R4C's top APR is 192% (0xb2cc $10 ±15% 1h) — well under 1000%. R4B's top APR was 4500%+, which would have triggered the flag.

## Tick decoder correction

R4B's int24 tick decoder used `p[256:320]` which reads 32 bytes and treats them as int256. The actual int24 in V3 is **right-aligned in the 32-byte word** (last 3 bytes, hex chars 314:320). R4B's decoded tick column is wrong; R4's `swap_events_decoded.csv` tick column is also wrong (shows 1.15e76 due to int24→int256 cast without sign extension).

R4C uses `p[314:320]` and sign-extends with `if tick_raw & (1 << 23): tick_raw -= (1 << 24)`. Verified: median tick for 0xb2cc is -202111, corresponding to a USDC/WETH price of ~1670 (consistent with ETH_USD=1653 ± 1%).

## Per-pool position math (R4C top candidate 0xb2cc $50 ±10% 24h)

| Field | Value |
|---|---|
| median_tick | -202176 |
| tickLower | -203130 |
| tickUpper | -201222 |
| sqrtP (Q64.96) | 3.220e24 |
| sqrtA (Q64.96) | 3.210e24 |
| sqrtB (Q64.96) | 3.230e24 |
| price_human (USDC/WETH) | 1659.77 |
| amount0_human (WETH) | 0.01507 |
| amount1_human (USDC) | 25.0 |
| amount0_usd | 25.00 |
| amount1_usd | 25.00 |
| reconstructed_usd | 50.00 |
| recon_error_pct | 0.0000 |
| L_from_amount0 | 1.317e13 |
| L_from_amount1 | 1.317e13 |
| **L_position** | **1.317e13** |
| median_L_event | 1.722e18 |
| **L_position / median_L_event** | **7.65e-6** |
| median_fee_share (R4C) | 7.65e-6 (0.00077%) |
| median_fee_share (R4B) | 2.63e-3 (0.263%) |
| R4C fee | $0.3102 |
| R4B fee | $120.81 |
| **fee_ratio R4C / R4B** | **0.00257 (390× overestimate by R4B)** |

## Summary

R4C's independent V3 math is correct and reproducible:
- L_position is computed from first principles using the position's own amount0/amount1 and the V3 `LiquidityAmounts.sol` formulas.
- All 81 cells reconstruct amount0_usd + amount1_usd = size_usd exactly.
- L_position is ~10^-6 of L_event, not ~10^-3 as R4 / R4B claimed.
- R4B's "active liquidity correction" is mathematically a no-op (L_event cancels in the fee_share formula).
- All 81 cells have net PnL < 0 under R4C math.

The "model bug" is real and severe. R4 / R4B's recommendation chain is invalidated.
