# Next Strategy Fork

## Current state

D1 — Delta-hedged LP feasibility — complete.
- Recommendation: NEED_MORE_DATA
- 6 sustainable cells under 0% and +5% funding (best: $1000 ±5% 24h 0xb2cc, net $0.68 at 0% funding)
- Min viable capital: $250
- Edge is thin (0.02-0.07% per day on size) and funding-dependent
- Current observed funding (-8% APR) wipes out the edge

## Recommended next stages

### D2 — Dynamic-delta rebalanced LP simulation (highest priority)

Goal: model the realistic case where the LP rebalances as tick moves. This is the difference between a static-range LP (degenerate) and a real LP (which would rebalance).

Approach:
- Use R4's per-event ticks to simulate a rebalanced LP
- For each block (or each event), check if current tick is in [tickLower, tickUpper]
- If not, exit (collect fees) and re-enter at a new position centered on current tick
- Track cumulative fees vs cumulative rebalance gas

If the rebalanced model shows positive net PnL where the static model didn't, the dynamic-delta thesis is viable.

### D3 — Funding rate history

Goal: quantify how often ETH funding has been favorable to SHORT positions over the last 30-90 days.

Approach:
- Pull 30d of 8h funding rates from Binance public `fapi/v1/fundingRate` endpoint (no auth)
- Compute % of time funding > 5% APR, > 0%, < 0%
- Compute average funding for the trailing 30d
- Compare to the spec's scenarios

If trailing 30d average funding is < 0% (i.e. shorts pay on average), the SHORT-thesis LP is structurally unviable.

### D4 — Per-pool volume / fee tier sensitivity

Goal: identify if any pool (including ones not in the R4C top 3) has higher fee capture that would make the delta-hedge model viable at smaller capital.

Approach:
- Re-run D1 with a wider pool set (top 10 by volume from R1)
- Re-run with a higher fee tier (1% instead of 0.05%) to see if the fee structure helps
- Report any pool that achieves GO at $50-$100 with sustainable funding

### Reward-only / new-pool alpha pivot (if D2-D4 don't help)

If the delta-hedged fee LP is structurally unviable, the next pivot is:
- **Reward-only**: focus on pools with token emissions (Aerodrome, Velodrome, etc.) where the LP earns the reward APR in addition to fees. The reward APR is the only thing that can make small positions viable.
- **New-pool alpha scanner**: identify new pools (TVL < $1M) where the L_position / L_event ratio is more favorable.

## What NOT to do next

- Do NOT proceed to live, canary, paper, mode B
- Do NOT write auto-exit engineering
- Do NOT read private keys, instantiate wallets, sign, or broadcast
- Do NOT touch CI, migrations, dashboard
- Do NOT use CEX/perp API keys (even read-only would require auth)

The freeze is preserved. Each D-stage requires explicit user authorization.
