# Delta-Hedged Decision — D2

## Final recommendation: GO_DELTA_HEDGED_LP_PLAN_ONLY

### Why GO and not NEED_MORE_DATA

D2 satisfies all GO criteria:
- ✓ At least one cell has positive net under median funding history: 16 cells
- ✓ Remains positive under unfavorable funding percentile: 16 cells at p5 stress
- ✓ Signal/noise >= 1.5: best cells 3.0-3.2
- ✓ Minimum viable capital <= $1000: $250
- ✓ Rebalance count reasonable: 1-7 per 24h for best cells
- ✓ No execution required in this stage
- ✓ Clear next plan exists: D3 (reward APR), D4 (paper validation)

### Why GO and not NO_GO

- The edge is robust to funding stress (16 cells at p5).
- The edge is robust to hedge strategy (static 0.75 wins, but static 0.5 + dynamic 0.57 also have positive cells at some sizes/ranges).
- The edge is robust to rebalance rule (`none`, `hourly`, `gt_1pct`, `gt_2pct` all have positive cells).
- The min viable capital is below $1000.

### Why GO_DELTA_HEDGED_LP_PLAN_ONLY and not immediate live

D2 is a static replay using R4's 24h data + historical funding. The recommendation is "plan only" because:
- The reward APR (Aerodrome emissions) is not modeled. This is the biggest missing factor for the live EV.
- The actual execution costs (slippage, market impact on the SHORT, rebalance tx size) are not modeled.
- A paper / shadow run is needed to validate the model in real time before any live probe.

## Recommended next stages (no execution now)

### D3 — Reward APR + delta-hedge
Add the Aerodrome (and PancakeSwap if applicable) reward APR to the model. Reward-only positions are sometimes the dominant source of LP income; the fee income is secondary. If rewards add 5-20% APR, the position becomes much more attractive.

### D4 — Paper / shadow validation
Run the highest-conviction cell (0xb2cc $1000 ±2% with 0.75 hedge and gt_2pct rebal) in a paper / shadow mode for 7d. Track actual fees, IL, rebalance events, and funding. Compare to the model's predictions.

### D5 — Live probe (only after D3 + D4 confirm)
If D3 + D4 confirm the edge, propose a tiny live probe with auto-exit wiring. The probe would be:
- $100-$250 LP on 0xb2cc
- 0.75 hedge on Hyperliquid (or similar low-fee perp)
- gt_2pct rebalance rule
- 7d hold maximum
- IL stop at -5%, time stop at 7d, fee-zero stop at 24h with no fees

Each stage requires explicit user authorization.

## What is NOT authorized

- No live, canary, paper, mode B at this stage
- No wallet, signer, private key
- No CEX/perp API key
- No trading, no order placement, no signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No auto-exit engineering yet (this is part of the next stage)
- No tiny live probe (this requires D3 + D4 confirmation first)

The freeze is preserved. D3 (reward APR) is the next research stage and requires explicit user authorization.
