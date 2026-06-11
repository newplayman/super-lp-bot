# Top Candidates — R2 (repriced)

**Stage:** `LP_BOT_STRATEGY_EVIDENCE_R2_GAS_ANCHOR_AND_AERODROME_REWARD_RECOVERY_V1`
**Run ID:** 20260611_064703

## Top 10 (by R2 expected net at $50 × 7d)

| Rank | Pool | Pair | Protocol | R1 net | R2 net | R2 verdict |
|---|---|---|---|---|---|---|
| 5 | `0xb94b2233…` | cbBTC / USDC 0.01% | pancakeswap-v3-base | $0.2052 | **$8.7409** | GO (50×7d), GO (10×24h) |
| 10 | `0x7501bc8b…` | msUSD / USDC 0.05% | aerodrome-slipstream | $0.0904 | **$8.2857** | GO (50×7d), GO (10×24h) |
| 23 | `0x74f72788…` | msETH / WETH 0.05% | aerodrome-slipstream | $0.0 | **$3.7596** | GO (50×7d), GO (10×24h) |
| 1 | `0xb2cc224c…` | WETH / USDC 0.05% | aerodrome-slipstream | $0.3988 | **$2.6158** | GO (50×7d), NO_GO (10×24h) |
| 17 | `0x42d4a22c…` | cbBTC / WETH 0.05% | aerodrome-slipstream | $0.0 | **$2.5655** | GO (50×7d), NO_GO (10×24h) |
| 2 | `0x72ab388e…` | WETH / USDC 0.01% | pancakeswap-v3-base | $0.0485 | **$2.561** | GO (50×7d), NO_GO (10×24h) |
| 6 | `0x3f9b863e…` | WETH / cbBTC 0.05% | hydrex-integral | $0.1914 | **$2.3898** | GO (50×7d), NO_GO (10×24h) |
| 7 | `0xfbb6eed8…` | cbBTC / USDC 0.05% | uniswap-v3-base | $0.0993 | **$2.2592** | GO (50×7d), NO_GO (10×24h) |
| 4 | `0x4e962bb3…` | cbBTC / USDC 0.05% | aerodrome-slipstream | $0.0422 | **$2.1999** | GO (50×7d), NO_GO (10×24h) |
| 16 | `0xc211e1f8…` | cbBTC / WETH 0.01% | pancakeswap-v3-base | $0.0 | **$2.1343** | GO (50×7d), NO_GO (10×24h) |

## Notes

- All "R2 net" values use the R2-observed gas anchor: $0.0795/cycle at 0.05 gwei.
- R1 net used the R1 model: $0.30/cycle (hand-estimate, 3.8× too pessimistic).
- R2 net is uniformly $0.22 better than R1 net for the same pool × size × hold.
- The 3 R1 top pools remain the 3 R2 top pools (Aerodrome Slipstream WETH/USDC 0.05%, PancakeSwap V3 WETH/USDC 0.01%, PancakeSwap V3 WETH/USDC 0.05%).
- R2's gas-anchor correction does NOT promote any pool from NO_GO to GO at $10 × 24h; the 24h fee yield is still insufficient to cover the (smaller) gas cost. Specifically: a $10 position earns ~$0.07/day in fees, minus $0.08 gas = -$0.01 net. R1 said -$0.27 net for the same case; R2 says -$0.01.
