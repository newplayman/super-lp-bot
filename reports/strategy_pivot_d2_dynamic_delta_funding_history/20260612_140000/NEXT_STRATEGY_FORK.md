# Next Strategy Fork — D2

## Current state

D2 — Dynamic delta + funding history — complete.
- Recommendation: GO_DELTA_HEDGED_LP_PLAN_ONLY
- 16 cells positive at median funding, 16 at p5 stress
- Min viable capital: $250
- Best cell: $1000 ±2% on 0xb2cc, 0.75 hedge, gt_2pct rebalance, net $6.83/day

## Recommended next stages

### D3 — Reward APR (Aerodrome emissions) — highest priority

Goal: add the reward APR (Aerodrome AERO emissions) to the model. Reward-only positions are the dominant source of LP income for many pools. If AERO rewards are 10-30% APR, the position becomes significantly more attractive.

Approach:
- Pull Aerodrome's gauge contracts (e.g. via `getRewardRate` or `rewardRate` from the gauge contract) — this requires a read-only Base RPC call (no auth, public endpoint).
- Compute reward APR = (AERO_per_second × AERO_USD_price) / TVL.
- Add to the D2 model as an additional revenue stream.

If the reward APR is meaningful, the GO recommendation strengthens. If it's zero (e.g. gauge not active), the recommendation reverts to NEED_MORE_DATA.

### D4 — Paper / shadow validation

Goal: validate the model in real time without committing capital.

Approach:
- Set up a paper tracker that simulates a $1000 LP on 0xb2cc with 0.75 hedge and gt_2pct rebalance.
- Track actual fees, IL, rebalance events, and funding over 7d.
- Compare to the model's predictions.

This requires a real-time data feed (Base RPC for LP, perp for hedge, no auth for either).

### D5 — Live probe (only after D3 + D4 confirm)

If D3 + D4 confirm the edge:
- $100-$250 LP on 0xb2cc
- 0.75 hedge on Hyperliquid (0.02% taker fee)
- gt_2pct rebalance rule (rebalance on >2% price move, max 1-2 per day expected)
- 7d hold maximum
- Auto-exit: IL > 5%, time > 7d, fees = 0 for 24h, residual delta > X%

Auto-exit wiring is ~50-100 lines of Go. Blocked by the freeze; can be unblocked only after D3+D4.

### Reward-only / new-pool alpha pivot (if D3 doesn't add reward)

If the reward APR is zero or negligible:
- The fee-only path is stopped (R4C).
- The delta-hedged path has thin edge that may not survive execution costs.
- The next pivot is: explore pools with active reward emissions but low fee capture (different signal), or new pools with high fee tier.

## What NOT to do next

- Do NOT proceed to live, canary, paper, mode B at the D2 stage. The D2 GO is "plan only".
- Do NOT write auto-exit engineering yet (this is part of the D5 stage if D3+D4 confirm).
- Do NOT use CEX/perp API keys (read-only public endpoints are fine).
- Do NOT touch CI, migrations, dashboard.

The freeze is preserved. Each D-stage requires explicit user authorization.
