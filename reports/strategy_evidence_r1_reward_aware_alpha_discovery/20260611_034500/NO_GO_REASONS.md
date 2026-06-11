# No-Go Reasons — R1

**Of 35 risk-passed pools ranked, 25 are `NO_GO` and 7 are `NEED_MORE_DATA`. 3 are `GO_TINY_LIVE` (mechanically, at $50 × 7d; see `TINY_LIVE_DECISION.md` for the human-override note).**

## A. 25 `NO_GO` pools — categorised

### A.1 Stable-stable pairs (USDC/USDT, USDC/USDbC, USDC/DAI) — 5 pools

At 0.01% fee tier, the per-dollar-per-day fee yield is 0.04%-0.10%/day. Even at $50 × 7d, expected net is -$0.20 to -$0.25 (gas dominates; IL on stable pairs is also non-zero because of depeg events). Sample: `0x...USDC/USDT` at 0.01% with $0.10 fee/dollar/day × $50 × 7d = $0.035 fee income − $0.30 gas = -$0.27 net.

### A.2 Long-tail / non-bluechip pairs — 12 pools

The risk filter assigns +30 risk-score to any pair that is not (blue-chip+blue-chip, stable+L1 wrap, or AERO-paired). Examples: VIRTUAL/WETH, DEGEN/WETH, TOSHI/WETH, BRETT/WETH, MIGGLES/WETH. These pools have high fee income (often > 1%/day) but the model down-weights them for tiny-live safety. Even at $50 × 7d, the model says they pass the gas math; the `NO_GO` is risk-driven, not economics-driven.

### A.3 High-fee small pools with thin 7d volume — 4 pools

e.g. SKI/WETH at 1% fee tier, $50k TVL, $1.2M 24h volume. Passes gas at $10 × 7d, but 7d volume stability is unverified; the run treats pools with < 7d observation as `NO_GO`.

### A.4 Pools with insufficient symbol/fee data — 2 pools

DexScreener-only pools where `fee_tier_bps=0` after name-parse. Tagged `unknown_fee_tier` in risk filter; excluded from simulation. These are real Base pairs (e.g. some Uniswap V3 Base pools with 0.3% or 1% tier) but the run cannot model them honestly without the fee tier.

### A.5 Pairs with too-low TVL — 2 pools

TVL between $25k and $50k — passes the `$TVL >= 25_000` floor but flagged as `tvl_below_floor` in risk. The capital grid would still amortise gas at $50 × 7d for some of these, but TVL below the retail-LP impact threshold makes the model unreliable.

## B. 7 `NEED_MORE_DATA` pools — categorised

### B.1 cbBTC pairs (4 pools)

cbBTC/USDC 0.05% aerodrome, cbBTC/USDC 0.01% pancakeswap-v3, WETH/cbBTC 0.05% hydrex-integral, cbBTC/USDC 0.05% uniswap-v3-base.

The risk filter treats cbBTC as L1-wrap (giving it BLUE_CHIP status in `is_os`/`is_blue` checks) **but** it also gives +30 risk-score because cbBTC is *not* a stable, and the pair is therefore not blue-chip-blue-chip. The result: passes gas at $3-50 × 7d (varies), but the model says NEED_MORE_DATA because of the risk-score. **Reclassifying cbBTC as blue-chip would re-rank cbBTC/USDC 0.01% pancakeswap to GO_TINY_LIVE at $3 USDC × 7d — a *much* more interesting candidate.** This is a model call, not a data call.

### B.2 EURC / USDC (1 pool)

EURC is a smaller stablecoin. Lower volume (5.6M/24h). Passes gas at $25 × 7d but EURC is not a top-3 stable. NEED_MORE_DATA for a 30-day fee-yield study.

### B.3 VIRTUAL / WETH (1 pool)

VIRTUAL is a long-tail token. Risk filter passes (volume/TVL good, age > 14d), but the model down-weights it. NEED_MORE_DATA pending token-risk work.

### B.4 msUSD / USDC (1 pool)

MetaMask's USD stablecoin. Passes gas at $3 × 7d (the lowest threshold of the NEED_MORE_DATA set). Risk filter passes; but the model says NEED_MORE_DATA because msUSD is newer (msUSD was launched in 2024, ~1 year history). 

## C. The 3 `GO_TINY_LIVE` candidates (mechanical, not yet human-approved)

| rank | pool | MVS × hold | expected net | why it ranks 1/2/3 |
|---|---|---|---|---|
| 1 | 0xb2cc... (Aerodrome WETH/USDC 0.05%) | $25 × 7d | +$0.13 | deepest TVL, highest fee_apr_est |
| 2 | 0x72ab... (PancakeSwap V3 WETH/USDC 0.01%) | $25 × 7d | +$0.05 | second-deepest WETH/USDC TVL |
| 3 | 0xb775... (PancakeSwap V3 WETH/USDC 0.05%) | $50 × 7d | +$0.04 | third venue for diversification |

These are *mechanically* GO. Whether they should be *human*-approved is in `TINY_LIVE_DECISION.md`.

## D. Headline no-go for "tiny live at retail on Base today" (if we keep the $10 USDC × 24h band)

If the user's definition of "tiny live" is the original **$10 USDC × 24h** probe, then **0 pools pass**. The R0 conclusion is unchanged. To promote any pool to GO under that definition, we need either:

- Live gas measurement confirming <$0.05/cycle (impossible at 10 gwei × 420k gas on Base).
- A 0 gas-relayer infrastructure (not in scope).
- 24h hold with 0% gas cost on the LP cycle (also impossible).

The R1 answer to "what *would* make $10 USDC × 24h work?" is:

> A reward APR ≥ 2.5% *per day* on the underlying pool (above fee yield alone). 1% AERO emissions are public, but per-pool rates are gated behind the offline Aerodrome subgraph.

If R2 recovers the Aerodrome Voter address, we can re-test this and likely find 5-10 AERO-paired pools that promote to $10 USDC × 24h GO_TINY_LIVE.
