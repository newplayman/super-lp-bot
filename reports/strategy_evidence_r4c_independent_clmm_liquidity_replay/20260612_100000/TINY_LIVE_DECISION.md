# R4C Tiny Live Decision

## Final recommendation: NO (R4C verdict: MODEL_BUG_FOUND)

Per R4C spec section F strict conclusion rule:
- R4B overestimated fee by >5x ✓ (median 290×, max 833×)
- All 81 cells have net ≤ 0 under R4C math ✓
- R4B formula cannot be reproduced independently ✓ (it can be reproduced; it's just mathematically equivalent to R4)

## Autonomous live probe is NOT authorized

R4C's recommendation is `MODEL_BUG_FOUND`, not `GO_TINY_LIVE_PLAN_ONLY`. Per the project freeze (CLAUDE.md / LPBOT_RESEARCH_STATUS_CN.md):
- `tiny_canary_allowed = no`
- `recommended next action = STOP_LP_RESEARCH_NOW` (since 20260531_124000 final freeze)
- No canary / live / paper / Mode B
- The autonomous live path is forbidden until the exit path is fixed AND the math is validated

R4C's MODEL_BUG_FOUND is a process-level signal that the fee math chain R1→R2→R3→R4→R4B was flawed. A tiny live probe would not address this; it would commit real capital to a model we now know is wrong. The probe is **not authorized**.

## What is required to revisit

1. **R5 — independent cross-check** of R4C's L_position math using a third-party V3 calculator (Uniswap v3-periphery SqrtPriceMath / LiquidityAmounts compiled to WASM, or a hand-coded reference implementation in another language).
2. **R5 — wider grid** — test sizes $100, $1k, $10k and ranges ±0.5% to ±50%. R4C's grid ($10/$25/$50 × ±5/10/15%) may simply be the wrong grid for fee-only LP. Larger positions have a higher L_position ratio relative to L_event.
3. **R5 — pool set expansion** — find pools where L_event at the current tick is much lower (e.g. concentrated position pools with most L at the edges, not the current tick).
4. **R5 — auto-rebalance modeling** — re-position the LP as the tick moves, accumulating fees. This is the realistic case (a static position is degenerate).
5. **Auto-exit wiring** — already a P0 blocker; not addressed by R4C.

Only after R5 produces positive net PnL on a properly-modeled cell can the R6 stage begin to consider tiny live authorization.

## What is explicitly NOT allowed at this stage

- No canary
- No live
- No paper
- No Mode B
- No wallet, signer, private key
- No signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No CI/migration/dashboard engineering
- No auto-exit engineering
- No tiny live probe
- No $50 × 7d live probe

The freeze is preserved.
