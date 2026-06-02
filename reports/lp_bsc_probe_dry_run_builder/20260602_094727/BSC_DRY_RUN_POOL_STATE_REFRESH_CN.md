# BSC Dry-run — Pool State Refresh (read-only)

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: D
- run_id: `20260602_094727`
- rpc: publicnode (host_hash `5a701356`)
- chain_id: `56` (BSC)
- latest_block: `101860171`

## 池子元数据

| 字段 | 值 |
|---|---|
| pool_address | `0x172fcd41e0913e95784454622d1c3724f546f849` |
| token0 / symbol / decimals | `0x55d3...7955` USDT 18 |
| token1 / symbol / decimals | `0xbb4C...c095c` WBNB 18 |
| fee_raw / percent | `100` / **0.01%** |
| tick_spacing | `1` |
| active_liquidity (in active tick) | `3,709,045,338,100,587,065,880,575` |

## slot0

| 字段 | 值 |
|---|---|
| sqrtPriceX96 | `3044364141145900957604773888` (示例时刻；下游使用动态值) |
| tick (current) | **`-65180`** |
| observationIndex | `172` |
| observationCardinality / next | `2400 / 2400` |
| unlocked | `true` |

## 当前价格

| | |
|---|---|
| WBNB price in USDT | **`$676.96`** |
| token1 per token0 (human) | `0.00147718` WBNB / USDT |

## QuoterV2 报价（read-only `eth_call`）

| input | amountOut | gas estimate | ticks crossed |
|---|---|---|---|
| 5 USDT → WBNB | 7,385,xxx wei | ~91k | 1 |
| **10 USDT → WBNB** | **14,770,414,709,518,662** wei (≈ 0.01477 WBNB) | ~92k | 1 |
| 10 WBNB-equiv → USDT | 9,998,966,833,058,948,302 wei (≈ 9.999 USDT) | ~92k | 1 |
| **20 USDT → WBNB** | **29,540,826,358,236,257** wei (≈ 0.02954 WBNB) | ~93k | 1 |
| 20 WBNB-equiv → USDT | ~19.998 USDT | ~93k | 1 |

观察：10U / 20U 滑点 ≈ 0.01% (恰好等于 fee tier；表明此 notional 远小于 active tick liquidity，可忽略 price impact)。

## 通过判定

```text
all_core_fields_present       = true
quoter_v2_callable            = true
chain_id                      = 56 ✓
tick                          = -65180 ✓ (用作 Phase E tick range 基准)
tick_spacing                  = 1
active_liquidity              = 3.7e24 (容量充裕)
wbnb_price_in_usdt            = $676.96
wallet_or_tx_touched          = false
can_run_probe_now             = false
```

## 安全

```text
calls used:    eth_chainId, eth_blockNumber, eth_call (slot0/liquidity/fee/tickSpacing/token0/token1/decimals/symbol),
               QuoterV2.quoteExactInputSingle via eth_call
calls forbidden in this phase (and not used):  eth_sendTransaction / eth_sendRawTransaction / signTransaction / 任何 wallet 加载
```
