# BSC PancakeSwap V3 — 1池 24h fee velocity smoke

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- run_id: `20260602_060633`
- pool: `0x172fcD41E0913e95784454622d1c3724f546f849` (USDT/WBNB, fee_tier_raw=100)
- rpc_source: `public_fallback:bsc-rpc.publicnode.com` (host_hash=`5a701356`)

## 范围

| 字段 | 值 |
|---|---|
| from_block | `101806396` |
| to_block | `101835196` |
| window_blocks | `28800` |
| chunk_blocks | `4000` |
| chunk_count | `8` |

## 结果

| 字段 | 值 |
|---|---|
| selected_pool_loaded | `True` |
| raw_log_count | `49255` |
| decoded_log_count | `49255` |
| decode_errors | `0` |
| eth_getLogs_success | `True` |
| decode_success | `True` |
| unique_traders_approx | `1894` |
| volume_usd_proxy | `25416171.07` |
| pool_fee_usd_proxy | `2541.6171` |
| **smoke_pass** | **`True`** |

## Decoder

Topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83` (PancakeSwap V3 Swap).
ABI: `Swap(address indexed sender, address indexed recipient, int256 amount0, int256 amount1, uint160 sqrtPriceX96, uint128 liquidity, int24 tick, uint128 protocolFeesToken0, uint128 protocolFeesToken1)`.

价格 / 小数位用启发式（USDT=`$1`, WBNB=`$600`，皆为 18 decimals）。精确 USD 价值由 Phase 5 economics preview 接管。

## 安全

```text
wallet_or_tx_touched   = false
can_run_probe_now      = false
tiny_canary_allowed    = no
edge_proven            = no
```
