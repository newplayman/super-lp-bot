# Reward-Adjusted Decision — D3

## Final recommendation: GO_DELTA_HEDGED_REWARD_LP_PLAN_ONLY

### Why GO and not NEED_MORE_DATA

D3 satisfies all GO criteria:
- ✓ Observed reward APR available (63.52% from DefiLlama for 0xb2cc)
- ✓ At least one cell positive under median and p5 funding stress (6 cells at observed reward + median + p5)
- ✓ Signal/noise >= 1.5 (best cells 3.0-3.5)
- ✓ Min viable capital <= $1000 ($250)
- ✓ Reward claim gas does not erase edge (claim gas $0.10/day, total reward income $1.74/day at $1000)
- ✓ No execution required in this stage

### Why GO and not NO_GO_REWARD_LAYER

- Reward APR is observed (not a scenario assumption).
- The edge is robust to reward scenario: even at 0% reward, the cell is GO (D2 base case).
- Adding the observed 63.52% reward thickens the edge by 22% — significant.

### Why GO_DELTA_HEDGED_REWARD_LP_PLAN_ONLY and not immediate live

D3 is a static model using R4's 24h data + 89.3d funding history + observed reward APR. The recommendation is "plan only" because:
- DefiLlama's 63.52% is a 30-day rolling average; the realized 24h reward could vary.
- The auto-exit wiring is still missing (P0 from R3).
- The model is 24h-based; longer-hold dynamics are extrapolated.
- Actual execution costs (slippage on the SHORT, rebalance tx size, AERO claim mechanics) are not modeled.

A paper / shadow run is needed to validate the model in real time before any live probe.

## Recommended next stages (no execution now)

### D4 — Paper / shadow validation (highest priority)

Goal: validate the model in real time without committing capital.

Approach:
- Set up a paper tracker that simulates a $250-$1000 LP on 0xb2cc with 0.75 hedge and gt_2pct rebalance.
- Track actual fees, AERO rewards, IL, rebalance events, and funding over 7d.
- Compare to the model's predictions (target: 80% accuracy on net PnL).

This requires a real-time data feed (Base RPC for LP, perp for hedge, AERO for rewards). All are public, no-auth.

### D5 — Auto-exit wiring (engineering)

If D4 confirms, the next engineering stage is to wire the auto-exit:
- IL stop (close position if IL > 5%)
- Time stop (close position if held > 7d)
- Fee-zero stop (close position if fees = 0 for 24h)
- Reward-collection automation

~50-100 lines of Go. Blocked by the freeze; can be unblocked only after D4 confirms.

### D6 — Live probe (only after D4 + D5)

If D4 + D5 confirm, propose a tiny live probe:
- $100-$250 LP on 0xb2cc
- 0.75 hedge on Hyperliquid (0.02% taker fee)
- gt_2pct rebalance rule
- 7d hold maximum
- Auto-exit: IL > 5%, time > 7d, fees = 0 for 24h, residual > X%

Each stage requires explicit user authorization.

## What is NOT authorized

- No live, canary, paper, mode B at this stage
- No wallet, signer, private key
- No CEX/perp API key
- No trading, no order placement, no signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No auto-exit engineering yet (this is the next stage after D4)
- No tiny live probe (this requires D4 + D5 + explicit user authorization)

The freeze is preserved.
