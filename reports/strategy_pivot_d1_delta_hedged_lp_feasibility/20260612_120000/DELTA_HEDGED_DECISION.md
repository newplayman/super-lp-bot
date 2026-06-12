# Delta-Hedged Decision

## Final recommendation: NEED_MORE_DATA

### Why NEED_MORE_DATA and not GO_DELTA_HEDGED_LP_PLAN_ONLY

The spec's GO criteria are mostly met:
- ✓ At least one cell has positive net_pnl_hedged_usd (6 cells under 0% and +5% funding)
- ✗ signal_noise_hedged >= 1: marginal (~1.0-1.2 at the best cells; spec wants clear >= 1)
- ✓ Minimum viable capital <= $1000 ($250)
- ✓ Funding scenario remains positive under neutral and +5% APR funding
- ✓ No execution required
- ✓ Clear next plan exists

The signal/noise is the near-miss. At the 6 sustainable cells, signal/noise ranges from 1.18 to 1.24. The spec's >= 1 threshold is barely cleared, and the model has multiple unverified assumptions.

### Why NEED_MORE_DATA and not NO_GO_DELTA_HEDGED_LP

- ✗ No cell positive after hedge costs: ✗ (6 cells positive under 0% and +5% funding)
- ✗ Min viable capital > $1000: ✗ ($250)
- Partial: funding risk destroys edge — only at current -8% funding. The model finds edge at 0% and +5% funding.
- ✗ Residual risk too large: ✗ (residual is 1.6% of size for 75% hedge, vs 1.2% fee — comparable, not catastrophically large)

The 6 sustainable cells give a real (if thin) edge. The model is not a flat NO_GO.

### Why NEED_MORE_DATA and not PIVOT_REWARD_ONLY_OR_NEW_POOL_ALPHA

The fee-only path is stopped (R4C), and the delta-hedged fee path is marginal but not strictly unviable. The model finds an edge under realistic funding scenarios (0% to +5% APR). PIVOT would be appropriate only if the delta-hedged path were strictly unviable — it's not. The right call is to gather more data on the assumptions (volatility, funding persistence, IL accuracy) before pivoting.

## Required next steps (no execution)

1. **Multi-day R2 — dynamic delta simulation** with rebalancing. A static position underestimates IL; a rebalanced position would have lower IL but higher gas cost. Model this trade-off.
2. **Funding rate history** — pull 7d or 30d of ETH funding from a public source. The +5% to +20% scenarios assume sustained positive funding; verify how often that has been the case over the last 30-90 days.
3. **Realized vol calibration** — R4C used 4% daily σ. The model would improve with the actual realized vol over the same 24h window as the R4C replay.
4. **LVR cross-check** — D1's IL formula is a closed-form LVR approximation. Cross-check with a numerical simulation (LVR by integrating the GBM path through the range).
5. **Perp-specific execution** — what venue (Hyperliquid, OKX, Binance)? What slippage? What's the min trade size?

## What is NOT authorized

- No live, canary, paper, mode B
- No wallet, signer, private key
- No CEX/perp API key
- No trading, no order placement, no signing, no broadcasting
- No approve, mint, addLiquidity, removeLiquidity, collect, swap, bridge
- No paid RPC, no private RPC
- No auto-exit engineering
- No tiny live probe

The freeze is preserved.
