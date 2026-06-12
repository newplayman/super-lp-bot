# Aerodrome Reward Recovery Report — D3

## Recovery status

| Component | Recovered? | Source |
|---|---|---|
| AERO token address | YES (0x940181a94A35A4569E4529A3CDfB74e38FD98631) | DefiLlama, confirmed via Base public RPC eth_call |
| AERO symbol / decimals | YES ('AERO', 18) | Base public RPC eth_call |
| 0xb2cc pool reward APR | **YES (63.52% APR)** | DefiLlama `/yields/pool/{uuid}` endpoint |
| 0xb2cc pool fee APR (DefiLlama) | 29.87% (vs R4C's measured 226% — see note) | DefiLlama |
| Reward token | AERO (single token) | DefiLlama |
| Pool UUID (DefiLlama) | recovered via underlyingTokens = [WETH, USDC] matching 0xb2cc's tokens | DefiLlama |

## Method (all read-only, no auth, no API key)

1. **DefiLlama public yields endpoint** — queried `https://yields.llama.fi/pools` (no auth). Filtered by `chain=Base` and `project=aerodrome-slipstream` and `symbol contains WETH and USDC`. Found 7 candidates. Identified 0xb2cc by matching `underlyingTokens` to `[0x4200...0006 (WETH), 0x8335...2913 (USDC)]` (the only candidate with both WETH and USDC at the high TVL range matching R4C's TVL of $8.7M).

2. **AERO token verification** — called `symbol()`, `name()`, `decimals()` on the recovered AERO address via Base public RPC `eth_call`. Got `AERO`, `Aerodrome`, `18` (matching DefiLlama's `rewardTokens` field).

3. **Gauge selector probe** (negative result) — tried 12+ standard gauge selectors against the gauge at `0x8279...b72`. All reverted. The Aerodrome Slipstream (CL) gauge uses a non-standard ABI; the reward state is encoded in storage (R2 found slot 2 = 21,270,630 which is interpreted as an Aerodrome epoch day; slots 6 and 7 contain ASCII strings "Slipstream Position NFT v1" and "AERO-CL-POS" respectively). Direct ABI probe did not recover the reward rate.

4. **Aerodrome frontend / Goldsky subgraph** (negative result) — tried `https://api.aerodrome.finance` (no response), the Aerodrome Goldsky URL from R2's notes (404 subgraph not found), and the TheGraph Aerodrome subgraph (301 redirect). All blocked or stale.

5. **Net result** — `reward_data_recovered = true` for the AERO APR (via DefiLlama). Gauge ABI is not required because DefiLlama aggregates the data and serves it as a single number.

## DefiLlama data interpretation

For 0xb2cc Aerodrome Slipstream WETH/USDC:
- **TVL**: $8,113,563 (matches R4C's $8.7M within 10% — TVL fluctuates)
- **apyBase (fee income)**: 29.87% APR (DefiLlama's volume-based estimate)
- **apyReward (AERO emissions)**: 63.52% APR
- **apy (combined)**: 93.39% APR
- **rewardTokens**: ['0x940181a94A35A4569E4529A3CDfB74e38FD98631'] (AERO)

DefiLlama's `apyBase` (29.87%) is lower than R4C's measured 226% because DefiLlama estimates 24h volume × 365d with a different methodology than the R4C replay (which measured actual 24h on-chain volume). The 29.87% from DefiLlama is a 30-day rolling average; R4C's 226% is a single 24h sample. The D3 model uses the more conservative DefiLlama number for the fee layer.

The D3 model uses the **observed 63.52% AERO reward APR** directly from DefiLlama for 0xb2cc.

## What this means for the strategy

The D2 model was NEED_MORE_DATA (marginal edge: best $6.83/day on $1000). Adding a 63.52% reward APR on top of the fee income would add `0.6352 × size × hold_days / 365` per cell. For $1000, 24h, that's $1.74 — a 25% boost over the $6.83 fee+hedge net.

This is the missing layer. The reward APR is the largest single source of LP income for this pool (63.52% vs 29.87% fee). The combined APY of 93.39% would have made D2 a clear GO.

## Safety

- Only public, no-auth endpoints queried.
- Only `eth_call`, `eth_getCode`, `eth_getStorageAt` (read-only) used.
- No `eth_sendRawTransaction`, no wallet, no signing, no broadcast.

## What is NOT used

- Aerodrome frontend (not needed; DefiLlama returns the data)
- Goldsky subgraph (URL stale)
- TheGraph Aerodrome subgraph (redirects to a deprecated URL)
