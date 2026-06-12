# Swap Event ABI Probe — R4

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R4_SWAP_EVENT_FEE_REPLAY_24H_V1`
**Run ID:** 20260611_080000

## Approach

For each of the 3 top candidate pools, the R4 probe attempts to identify the **Swap event topic hash** by trying all plausible Swap event ABIs and selecting the one that returns the most events.

## Results

### 0xb2cc... (Aerodrome Slipstream WETH/USDC 0.05%)

| Topic | Match | Events in 1h (no-topic filter) |
|---|---|---|
| **0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67** | **Swap(address,address,int256,int256,uint160,uint128,int24)** | **28483 events in 24h** |
| 0x19b47279... (Algebra v2 Swap) | (rejected) | 0 |
| 0xf73649a1... (V3 extended) | (rejected) | 0 |

**ABI: standard Uniswap V3.** Topic0 = `keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")`.

Data layout (5 words, 32 bytes each):
- `amount0` (int256) — WETH (token0) delta (signed; positive = WETH in, negative = WETH out)
- `amount1` (int256) — USDC (token1) delta
- `sqrtPriceX96` (uint160)
- `liquidity` (uint128)
- `tick` (int24)

### 0x72ab... (PancakeSwap V3 WETH/USDC 0.01%)

| Topic | Match | Events in 1h |
|---|---|---|
| 0xc42079f9... (V3 standard) | (rejected — 0 events) | 0 |
| **0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83** | **Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)** | **80378 events in 24h** |
| 0x40d0efd1... (Collect) | (rejected) | 0 |
| 0xb9ff484a... (Burn) | (rejected) | 0 |

**ABI: Algebra V2 (PancakeSwap V3 fork).** Topic0 = `keccak256("Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)")`.

Data layout (7 words):
- `amount0`, `amount1`, `sqrtPriceX96`, `liquidity`, `tick` (same as V3)
- `feeZto` (uint128) — zero-to-one fee in token1 equivalent
- `feeOtz` (uint128) — one-to-zero fee

The extra 2 fee fields are **Algebra's per-swap fee tracker**, useful for direct fee accounting.

### 0xb775... (PancakeSwap V3 WETH/USDC 0.05%)

Same ABI as 0x72ab... (Algebra V2). 6819 events in 24h.

## Other events observed (PancakeSwap V3, not used in R4)

When pulling **all logs without topic filter**, the following additional topics appear on PancakeSwap V3 pools (and on Slipstream):

- `0x0c396cd9...` — appears on 0xb775 and 0xb2cc; 20/h on 0xb2cc, 5/h on 0xb775. Topics show 3 zero/MAX-tick markers. Likely Algebra V2 `ModifyLiquidity` event.
- `0x70935338...` — appears on 0xb775 and 0xb2cc. Data shows an address in word[0] (looks like a router/origin) and an amount in word[1] (USDC scale). Likely `ModifyLiquidity` with origin.
- `0x7a53080b...` — Standard V3 `Mint(address,address,uint256,uint256,uint256)` (PancakeSwap V3 fork version). 7 events/h on 0xb2cc, 2 events/h on 0xb775.

These are not used in R4's fee calibration (which is purely Swap-based), but they confirm the pool is being actively used.

## Final ABI assignment

| Pool | Swap topic | ABI | 24h events |
|---|---|---|---|
| 0xb2cc... | 0xc42079f9... | V3 standard | 28,483 |
| 0x72ab... | 0x19b47279... | Algebra V2 | 80,378 |
| 0xb775... | 0x19b47279... | Algebra V2 | 6,819 |
