# R4B Baseline Review — Why the "Active Liquidity Correction" Was a No-Op

R4B claimed to "correct" R4's fee replay by replacing `L_total` (pool-wide liquidity) with `L_event` (per-swap active liquidity) in the fee share denominator. R4C re-derives the math and shows the correction was mathematically a no-op.

## R4B's stated correction

R4B's Python code computes:

```python
base_share = (size / info["tvl_usd"]) * l_factor

for ev in window_events:
    L_event = ev["liquidity"]
    L_pos_e = base_share * L_event
    fee_share = L_pos_e / (L_event + L_pos_e)
    ...
```

R4B claimed the difference vs R4 was:
- R4: `fee_share = (size/TVL) * l_factor` (using L_total as denominator)
- R4B: `fee_share = base_share * L_event / (L_event + base_share * L_event) = base_share / (1 + base_share)`

## The cancellation

The `L_event` in `L_pos_e` cancels in the `fee_share` formula:

```
fee_share = (base_share * L_event) / (L_event + base_share * L_event)
         = (base_share * L_event) / (L_event * (1 + base_share))
         = base_share / (1 + base_share)
```

R4B's "active liquidity correction" reduces to the same `size/TVL × l_factor` shortcut, with a trivial `1/(1+x)` correction factor that is ≈ 1 when `size/TVL × l_factor << 1` (true for all $10–$50 sizes on these pools).

## R4B's own self-check confirms this

In R4B's `main()`:

> R4: fee_share = (size/TVL) * l_factor = 0.92% for $50 on $8.7M ±5%
> R4B: fee_share = (size/TVL) * l_factor / (1 + (size/TVL) * l_factor) = 0.96% for same

R4B then notes "Hmm, R4 was right after all" and proceeds to claim the "real difference" is using L_event from each swap. But that's a different axis (temporal variation of L, not the formula's structural dependency on L). And in practice, R4B's `median correction factor 0.9965` confirms R4 and R4B produce nearly identical numbers — because they are algebraically equivalent.

## R4C's actual independent math

R4C computes `L_position` from V3's `LiquidityAmounts.sol` formulas, which use `amount0` and `amount1` directly:

```
L_from_amount0 = amount0 * sqrtP * sqrtB / ((sqrtB - sqrtP) * 2^96)
L_from_amount1 = amount1 * 2^96 / (sqrtP - sqrtA)
L_position = min(L_from_amount0, L_from_amount1)
```

For a $50 position at 0xb2cc, split 50/50 by value at the current price:
- amount0_raw (WETH) ≈ 0.015 WETH (wei)
- amount1_raw (USDC) ≈ 25 USDC (raw 6 dec)
- L_from_amount0 = 0.015e18 * 3223e12 * 3223e12 / ((3223e12 - 3223e12*(1±0.10/2)) * 2^96) ≈ 1.3e13
- L_from_amount1 ≈ 25e6 * 2^96 / (sqrtP_diff) ≈ 1.3e13
- L_position ≈ 1.32e13

median L_event on 0xb2cc: 1.72e18.
ratio L_position / L_event: 7.7e-6.

R4 / R4B's `base_share × L_event` would give L_pos = 0.0026 × 1.72e18 = 4.47e15. The fee_share is then 4.47e15 / (1.72e18 + 4.47e15) = 0.0026 — which is the R4B answer.

But R4C says: L_position is 1.32e13, NOT 4.47e15. The R4 / R4B L_pos is 339× too high.

## Why the R4 / R4B shortcut fails

R4 / R4B treats `L_position = (size/TVL) × l_factor × L_event` as if the L_event here is the L the position would have if it had size=TVL liquidity. But L_event is the pool's current L, not the "unit L" that a $1 of capital would create. A $50 position creating its own L_position in V3 is a function of amount0/amount1/sqrtP/tickLower/tickUpper, not a function of pool-wide L.

In V3:
- L_event at the current tick = sum of L of all positions whose [tickLower, tickUpper] contains the current tick
- L_position for a new $50 position = derived from the position's own amount0/amount1

These are different quantities. A $50 position's L_position is a small number (~1e13 for the top candidate), not a fraction of the pool's L_event.

## Conclusion

R4B's active-liquidity correction was mathematically equivalent to R4's fee share. R4C's independent L_position math shows the R4 / R4B shortcut overestimates fee share by 100–1000×. R4C's recommendation is MODEL_BUG_FOUND per the R4C spec's strict conclusion rule.
