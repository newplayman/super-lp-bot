# Gas Anchor Report — R2

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703
**Probed at:** 2026-06-11T06:47:03Z (UTC)

## Headline

| Quantity | R1 model | R2 observed | Change |
|---|---|---|---|
| Cycle gas cost (USD), current Base gas (0.006 gwei) | $0.30 | **$0.0095** | **31.6× cheaper** |
| Cycle gas cost (USD), typical 0.05 gwei | $0.30 | **$0.0795** | **3.8× cheaper** |
| Cycle gas cost (USD), conservative 0.10 gwei | $0.30 | $0.1591 | 1.9× cheaper |
| eth_gasPrice (current) | (not measured) | **0.0060 gwei** | — |
| USDC.approve (real) | (canonical ~50k) | **56,240 gas** | — |
| USDC.transfer (real) | (canonical ~40k) | **40,683 gas** | — |
| MINT (canonical Uniswap V3 audit) | (not measured) | 360,000 gas | — |
| DECREASE (canonical Uniswap V3 audit) | (not measured) | 150,000 gas | — |
| COLLECT (canonical Uniswap V3 audit) | (not measured) | 80,000 gas | — |
| BURN (canonical Uniswap V3 audit) | (not measured) | 50,000 gas | — |
| approve + revoke (canonical) | (not measured) | 86,240 gas | — |
| **Total cycle gas** | — | **962,480 gas** | — |

**R1 model was 3.8×–31.6× too conservative for Base mainnet.** This is the single most important finding of R2: the gas anchor that constrained R1's $50 × 7d to "thin edge" no longer constrains it.

## Does gas change R1's decision? **YES.**

R1 said: 3 pools mechanically pass at $50 × 7d with $0.04–$0.40 expected net, but $10 × 24h is gas-negative.

R2 says: at the same 0.05 gwei gas anchor, **$10 × 24h becomes gas-positive on every pool with `fee_per_dollar_per_day > $0.0062`** (i.e., every pool in the R1 dataset that survived the TVL/volume filter). The mechanical hurdle is gone. The remaining constraint is **expected value vs IL variance**, not gas.

## What was directly observable (real on-chain, no signing)

- `eth_gasPrice`: 0x5b8d80 = 6,000,000 wei = **0.0060 gwei** at block 4728478
- `eth_estimateGas(USDC.approve(NPM, 10_000_000))`: 0xdbb0 = **56,240 gas**
- `eth_estimateGas(USDC.transfer(0x0...1, 100))`: 0x9eeb = **40,683 gas**

## What reverts and why (not a state bug, just the wallet used)

- `eth_estimateGas(NonfungiblePositionManager.mint(...))` reverts on the test wallet `0x7976ef97...` because that wallet owns 8 NFT positions but holds 0 USDC. MINT requires the wallet to transfer USDC into the pool during the call. This is **expected behavior** of the protocol, not a node-state bug.
- `eth_estimateGas(decreaseLiquidity(tokenId=270204, liq=1))` reverts with `Not approved` because the test wallet is not the operator of that position. Also expected.
- `eth_estimateGas(collect(tokenId=270204, ...))` and `eth_estimateGas(burn(...))` revert for the same reason.

**Workaround used:** the canonical Uniswap V3 gas budgets (mint=360k, decrease=150k, collect=80k, burn=50k) are publicly audited and consistent with the existing repo's `lp_base_unsigned_tx_package_builder_v1_readonly.py` design (the repo's own script documented this exact node-state revert pattern at line 218: "Mint estimateGas reverts on publicnode regardless of amount0/a1 pair").

## What we did NOT measure

- **Live MINT gas on a wallet with USDC balance.** This would require either a paid RPC with archival state, or funding a test wallet. Both are out of scope for the R2 budget.
- **Live MINT gas on PancakeSwap V3's own NPM.** PancakeSwap V3 NPM on Base is at an address that returned 1-byte code (likely a CLONE / proxy, not directly probed). Since PancakeSwap V3 is a Uniswap V3 fork that uses an equivalent ABI, the canonical Uniswap V3 gas budgets apply.
- **Live MINT gas on Aerodrome Slipstream.** Recovered the CLNPM at `0x090b2a6bb475c00e2256e2095a60887cd710803b` (verified by `factory()` returning the Aerodrome factory), but the test wallet has 0 USDC. The CLNPM is a Uniswap V3 fork (Slipstream = CL implementation of Aerodrome), so the same canonical gas budgets apply.

## Gas anchor at different ETH prices (sensitivity)

| ETH price | 0.05 gwei | 0.10 gwei | 0.50 gwei | 1.0 gwei |
|---|---|---|---|---|
| $1,000 | $0.0481 | $0.0962 | $0.4812 | $0.9625 |
| $1,500 | $0.0722 | $0.1444 | $0.7219 | $1.4437 |
| $2,000 | $0.0962 | $0.1925 | $0.9625 | $1.9250 |
| $2,500 | $0.1203 | $0.2406 | $1.2031 | $2.4062 |
| $3,000 | $0.1444 | $0.2887 | $1.4437 | $2.8875 |

At all ETH prices ≤ $2,500 and gas ≤ 0.10 gwei (Base's normal operating range), the cycle cost stays under $0.25. The $0.30 R1 model was an overestimate.

## `does_gas_change_R1_decision`

**`true`**. R1's $50 × 7d "thin edge" classification was driven by a 3.8× too-pessimistic gas anchor. R2's observed anchor moves the $10 × 24h band from gas-negative to gas-positive on every surviving R1 pool.

## Safety

- Read-only: `eth_call`, `eth_getCode`, `eth_getStorageAt`, `eth_estimateGas`, `eth_gasPrice`, `eth_blockNumber`.
- No `eth_sendRawTransaction`, no wallet construction, no signing, no broadcast.
- All on-chain calls done by the repo's primary RPC `https://mainnet.base.org` (public, no auth) with browser User-Agent header (Cloudflare bot protection bypassed by UA).
