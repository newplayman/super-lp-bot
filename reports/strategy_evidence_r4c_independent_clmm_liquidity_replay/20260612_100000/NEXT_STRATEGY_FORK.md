# Next Strategy Fork

## Current state

R1 → R2 → R3 → R4 → R4B → R4C complete.
- R1: fee proxy = (size/TVL) × l_factor × proxy_volume
- R2: gas + reward reprice (volume overestimated)
- R3: real-fee exit readiness (auto-exit missing)
- R4: 24h Swap event replay using L_total
- R4B: 24h Swap event replay with L_event (mathematically equivalent to R4)
- R4C: independent V3 L_position math → **MODEL_BUG_FOUND**

R4C's verdict invalidates the R1→R4B recommendation chain. The fee-only LP path at $10–$50 sizing on the current 3 pools is not viable under proper CLMM math.

## Recommended next stages

### R5 — Independent V3 calculator cross-check (highest priority)

Goal: confirm R4C's L_position math is correct using a third-party V3 implementation, and re-test a wider grid.

Approach options:
1. **Compile Uniswap v3-periphery to WASM** — write a small TypeScript script that imports `@uniswap/v3-periphery` and uses `LiquidityAmounts.getLiquidityForAmount0` and `getLiquidityForAmount1` to recompute L_position for the 81 cells.
2. **Use v3-sdk** — write a Node script using the official `@uniswap/v3-sdk` and `computePoolAddress` to derive L_position.
3. **Hand-coded reference in another language** — Rust / Solidity / Go (we have `pkg/tickmath` in the project) — implement the same formulas and compare.

R5 should:
- Use the same 24h R4 Swap event JSONL files
- Re-derive L_position for the same 81 cells using the third-party calculator
- Compare L_position to R4C's L_position; report agreement/disagreement
- If agreement, also test the wider grid ($100, $1k, $10k × ±0.5%, ±1%, ±2%, ±5%, ±10%, ±25%, ±50%) to find a cell with positive net PnL
- If disagreement, the third-party is the tie-breaker; document which is correct

### R5 — Pool set expansion

Current 3 pools all have L_event ~ 1e18 (high active L). Test pools with L_event < 1e15 to see if the L_position / L_event ratio improves enough to make fee capture meaningful.

Candidates (low-L pools):
- Aerodrome Slipstream pairs with thin L (e.g. long-tail WETH pairs)
- PancakeSwap V3 pairs with concentrated L (mostly positions far from current tick)
- Uniswap V3 pairs on Base with low TVL

### R5 — Auto-rebalance modeling

Static-position modeling is unrealistic. A real LP re-positions as tick moves. Model:
- Each block, check if current tick is still in [tickLower, tickUpper]
- If not, exit (collect fees) and re-enter at a new position centered on current tick
- Track gas cost of rebalance
- Compare cumulative fees vs static-position fees

This is more complex but more realistic. A static position in a high-volume pool will be in-range 0% of the time unless the range is huge.

### R6 — Auto-exit wiring (still a P0 blocker)

Independent of fee math, the auto-exit is missing:
- IL stop (close position if IL > threshold)
- Time stop (close position if held > N days)
- Fee-zero stop (close position if fees collected = 0 in last M hours)

~50-100 lines of Go, blocked by the freeze. Should be unblocked only after the fee math is validated.

### R7 — Long-horizon 7d+ observation

R4's 24h is a single realization. R7 would extend the Swap event extraction to 7d or 30d to smooth variance. This was R5 in the previous strategy fork, but it's lower priority than the R4C model-bug fix.

## What NOT to do next

- Do NOT proceed to canary / live / paper / tiny live probe
- Do NOT write auto-exit engineering yet
- Do NOT promote R4B's GO / NEED_MORE_DATA conclusions (they are based on a flawed model)
- Do NOT read private keys, instantiate wallets, sign, or broadcast
- Do NOT touch CI, migrations, dashboard

The freeze is preserved. Each R-stage requires explicit user authorization.
