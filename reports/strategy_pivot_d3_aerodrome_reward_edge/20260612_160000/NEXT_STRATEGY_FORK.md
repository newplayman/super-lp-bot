# Next Strategy Fork — D3

## Current state

D3 — Reward-adjusted delta-hedged LP — complete.
- Recommendation: GO_DELTA_HEDGED_REWARD_LP_PLAN_ONLY
- 222 GO cells across the 2,700-cell matrix
- Best cell: 0xb2cc $1000 ±2% 24h, 0.75 hedge, median funding → $8.32/day
- Min viable capital: $250 → $1.83/day
- Reward APR observed: 63.52% (DefiLlama)

## Recommended next stages

### D4 — Paper / shadow validation (highest priority)

Goal: validate the model in real time. The D3 model is based on a single 24h sample. D4 would run the model for 7d in real time and compare.

Approach:
- Set up a paper tracker for a $250 LP on 0xb2cc ±2% with 0.75 hedge.
- Read R4-style swap events from Base RPC (read-only) every block.
- Compute the actual fee + reward + funding + IL for each event.
- Track rebalance events, claim events, and net PnL.
- Compare to the D3 model predictions.

If D4 confirms the model within 20%, proceed to D5. If D4 shows large deviation, return to NEED_MORE_DATA.

### D5 — Auto-exit wiring (engineering)

If D4 confirms:
- Add IL stop, time stop, fee-zero stop to `internal/core/execution/`.
- ~50-100 lines of Go.
- Tests in `tests/property/` for the exit conditions.

Blocked by the freeze; can be unblocked only after D4 confirms.

### D6 — Live probe (only after D4 + D5)

If D4 + D5 confirm:
- $100-$250 LP on 0xb2cc
- 0.75 hedge on Hyperliquid (or similar low-fee perp)
- gt_2pct rebalance rule
- 7d hold maximum
- Auto-exit on IL > 5%, time > 7d, fees = 0 for 24h

The probe is the first stage that touches real money. It requires:
- Wallet instantiation
- CEX/perp API key
- Real execution (addLiquidity, swap, etc.)

This is the threshold that requires explicit user authorization beyond the research stages.

### PIVOT_NEW_POOL_ALPHA_SCANNER (if D4 fails)

If D4 shows large model deviation or the reward APR drops:
- The fee-only path is stopped (R4C).
- The delta-hedged reward path is no longer GO (D4 reverted).
- The next pivot is: scan for new pools with higher reward APY (Aerodrome emissions change weekly; PancakeSwap incentives; Balancer gauges; Curve rewards).

This would be a scanner stage, not a fixed-pool stage.

## What NOT to do next

- Do NOT proceed to live, canary, paper, mode B at the D3 stage. The D3 GO is "plan only".
- Do NOT write auto-exit engineering yet (this is part of the D5 stage if D4 confirms).
- Do NOT use CEX/perp API keys (read-only public endpoints are fine).
- Do NOT touch CI, migrations, dashboard.

The freeze is preserved. Each D-stage requires explicit user authorization.
