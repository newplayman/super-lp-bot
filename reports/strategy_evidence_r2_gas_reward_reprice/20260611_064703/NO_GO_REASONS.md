# No-Go Reasons — R2

**Of 35 risk-passed pools repriced, all 25 R1 NO_GO pools remain NO_GO, and the 3 R1 GO_TINY_LIVE candidates remain GO at $50 × 7d (with a wider comfort zone thanks to the R2 gas anchor).**

## A. 25 R1 `NO_GO` pools — R2 re-check

### A.1 Stable-stable pairs (USDC/USDT, USDC/USDbC, USDC/DAI) — 5 pools

R1 said: $0.20-$0.25 negative net at $50 × 7d. R2 says: **$0.02-$0.03 positive net** at $50 × 7d.

The R2 gas correction moves these pools from NO_GO to marginal-GO on the gas-math alone. They remain risk-driven NO_GO (depeg risk, low fee yield), but the gas-side blocker is gone.

### A.2 Long-tail / non-bluechip pairs — 12 pools

R1 said: risk-driven NO_GO. R2 says: **same**, plus the gas correction makes the fee math pass on most of them (e.g. $50 × 7d on TOSHI/WETH goes from -$0.27 to -$0.05). These pools are mechanically profitable on fees but the risk model down-weights them. R2 does not re-classify any token's risk level.

### A.3 High-fee small pools with thin 7d volume — 4 pools

Unchanged. R2 cannot validate 7d volume stability from a single data snapshot.

### A.4 Pools with insufficient symbol/fee data — 2 pools

Unchanged. R2 cannot recover fee tier data; this is a model-input gap, not a gas or reward gap.

### A.5 Pairs with too-low TVL — 2 pools

Unchanged. R2 does not re-evaluate TVL; the R1 risk filter is still in effect.

## B. 7 R1 `NEED_MORE_DATA` pools — R2 re-check

### B.1 cbBTC pairs (4 pools) — R1 said NEED_MORE_DATA, R2 says same

- cbBTC/USDC 0.05% aerodrome (rank 4): R1 net = -$0.04, R2 net = +$0.18 at $50 × 7d. **Moves from gas-NO_GO to gas-GO**, but the cbBTC risk classification keeps it at NEED_MORE_DATA.
- cbBTC/USDC 0.01% pancakeswap-v3 (rank 5): R1 net = -$0.05, R2 net = +$0.20 at $50 × 7d. Same pattern: gas-GO, risk-NEED_MORE_DATA.
- WETH/cbBTC 0.05% hydrex-integral (rank 6): same.
- cbBTC/USDC 0.05% uniswap-v3-base (rank 7): same.

If cbBTC were re-classified as blue-chip (model call, not data call), these 4 would all become GO_TINY_LIVE.

### B.2 EURC / USDC (1 pool) — R1 said NEED_MORE_DATA, R2 says same

EURC is a smaller stablecoin. R1 net = -$0.10, R2 net = +$0.10 at $25 × 7d. Gas is now fine; the blocker is "smaller stablecoin" which is a model call.

### B.3 VIRTUAL / WETH (1 pool) — R1 said NEED_MORE_DATA, R2 says same

VIRTUAL is long-tail. R1 net = -$0.24, R2 net = -$0.02 at $50 × 7d. The R2 gas correction moves the gas-side closer to breakeven, but the token-risk model keeps this at NEED_MORE_DATA.

### B.4 msUSD / USDC (1 pool) — R1 said NEED_MORE_DATA, R2 says same

msUSD is newer. R1 net = -$0.20, R2 net = -$0.06 at $3 × 7d. R2 widens the gas-side but the "newer stablecoin" model call keeps it at NEED_MORE_DATA.

## C. The 3 R1 `GO_TINY_LIVE` candidates — R2 re-check

| Rank | Pool | R1 MVS × hold | R2 MVS × hold | R1 net @ 50×7d | R2 net @ 50×7d |
|---|---|---|---|---|---|
| 1 | 0xb2cc... (Aerodrome WETH/USDC 0.05%) | $25 × 7d | **$3 × 7d** | +$0.40 | **+$0.62** |
| 2 | 0x72ab... (PancakeSwap V3 WETH/USDC 0.01%) | $25 × 7d | **$3 × 7d** | +$0.05 | **+$0.27** |
| 3 | 0xb775... (PancakeSwap V3 WETH/USDC 0.05%) | $50 × 7d | **$10 × 7d** | +$0.04 | **+$0.25** |

All 3 remain GO at the R2 MVS threshold. The R2 widening of MVS is the headline gas-anchor win.

These are *mechanically* GO. Whether they should be *human*-approved is in `TINY_LIVE_DECISION.md`.

## D. R2's verdict on "tiny live at retail on Base today" (if the user's definition is $10 USDC × 24h)

R1: 0 pools pass. R2: **0 pools pass** (the 24h fee yield on $10 is still smaller than $0.08 gas).

The path to making $10 × 24h work is **reward data**, not gas. If the Aerodrome AERO emissions are ≥0.5% APR (rough estimate), then the AERO-paired pools could add ~$0.014/day on $10, which is not enough alone. The actual path to $10 × 24h would require (a) a 0% gas relayer (e.g., an account-abstraction wallet that sponsors the cycle), or (b) a much higher reward rate than 0.5% APR, or (c) a model that accepts a small negative EV as "data collection cost".

R2 does not change this $10 × 24h verdict — the gas correction is too small at this band.

## E. R2's verdict on "tiny live at retail on Base today" (if the user's definition is $50 USDC × 7d)

R1: 3 pools pass. R2: **3 pools pass** (the same 3, with a wider MVS, and $0.22 more expected net per pool).

This is the band where the recommendation could be GO_TINY_LIVE if IL variance were addressable (see TINY_LIVE_DECISION.md). R2 narrows the path forward to either IL-hedge design or cbBTC re-classification.
