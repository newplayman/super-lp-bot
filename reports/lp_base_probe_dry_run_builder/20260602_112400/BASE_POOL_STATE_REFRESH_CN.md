# Base 池状态刷新

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: F
- run_id: `20260602_112400`
- wallet_address_masked: `0xb05b...d835`
- frozen_pool: `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38`
- rpc: `https://base-rpc.publicnode.com` (host_hash=`7d4aef4d`)

## Block 锁定

| 字段 | 值 |
|---|---|
| block_number | **46807634** |
| block_hex | `0x2ca3a52` |
| 相对 Phase E 差 | +503 blocks（约 2-3 min fresh） |

## Pool 身份校验

| 字段 | 期望 | 观察 | 通过 |
|---|---|---|---|
| token0 | `0x4200...0006` (WETH) | `0x4200...0006` | ✓ |
| token1 | `0x8335...2913` (USDC) | `0x8335...2913` | ✓ |
| fee | 100 (0.01%) | 100 | ✓ |
| tick_spacing | 1 | 1 | ✓ |
| token_order_consistent_with_freeze | true | true | ✓ |

## Pool 状态 (slot0 + liquidity)

| 字段 | 观察 |
|---|---|
| sqrtPriceX96 | 3,519,976,964,698,468,343,876,834 |
| current_tick (int24, signed) | **-200,443** |
| observation_index | 755 |
| observation_cardinality | 1000 |
| observation_cardinality_next | 1000 |
| fee_protocol | 216,272,100 |
| unlocked | true |
| current_liquidity | 965,864,593,201,743,462 |

相对 upstream `v3_tick_liquidity_v2` (block 46766428) drift：
- tick: -200503 → **-200443** (+60 ticks 漂移 = $0.13 USD 漂移)
- current_liquidity: 454,933,522,258,074,128 → **965,864,593,201,743,462** (大幅增加 = 池内 LP 增加 ~2.1x)

## Price anchor (slot0 → WETH USD)

| 字段 | 值 |
|---|---|
| 公式 | `price_token1/token0_human = (sqrtPriceX96^2 / 2^192) * 10^(decimals0 - decimals1)` |
| decimals0 - decimals1 | 18 - 6 = 12 |
| price_token1_per_token0_raw | 1.9739e-9 |
| **weth_usd_anchor** | **$1,973.88** |

相对 upstream `v3_tick_liquidity` 同一池 slot0 隐含 anchor: `1979.86`. 差 **-$5.98 = -0.30%**。基本一致（slot0 是动态的，每次 block 都可能动一点点）。

## QuoterV2 live re-read 状态

| 字段 | 值 |
|---|---|
| 状态 | **skipped_due_to_publicnode_revert** |
| 原因 | Uniswap V3 QuoterV2 (`0x3d4e..`) 与 Aerodrome Slipstream Quoter (`0x254c..`) 在 publicnode 上对 selector `f7729d43` (`quoteExactInputSingle(address,address,uint24,uint256,uint160)`) 都 revert。publicnode 免费 tier 可能限流 / 过滤此调用 |
| 拒绝编造 | `fabrication_blocked = true`（不构造、不重试、不回退到非标准 selector） |
| 继承 | `reports/lp_precise_quote/20260601_120001/precise_quote_results.csv` 中同一池同一 notional 的 row |

### Inherited 20U result (from upstream precise_quote block 46762944)

| 字段 | 值 |
|---|---|
| notional | 20 USD |
| quote_side | token0_to_token1 (WETH -> USDC) |
| amount_in_raw (WETH) | 10,095,282,979,808,746 (≈ 0.01009 WETH = $20) |
| amount_out_raw (USDC) | 19,966,663 (≈ $19.97) |
| slippage_pct | 0.167% |
| ticks_crossed | 0 |
| gas_estimate | **203,739** |
| confidence | high |
| sqrt_price_x96_after | 3,523,555,858,135,066,593,060,566 |

### Inherited 10U result

上游 CSV 不含 10U 行（仅 {20, 100, 500, 1000, 2000}）。Phase H 用**线性外推**估算 10U：
- 20U amount_in = 0.01009 WETH → ticks_crossed=0
- 10U 严格更小 → ticks_crossed 仍 0；amount_out 严格线性 → ≈ 9,983,331 USDC raw ≈ $9.98

## 已用 RPC（read-only）

- `eth_chainId`
- `eth_blockNumber`
- `eth_call slot0()`
- `eth_call liquidity()`
- `eth_call token0()` / `token1()` / `fee()` / `tickSpacing()`
- `eth_call quoteExactInputSingle` × 2 notionals × 2 directions = 4 calls (reverted, 跳过)

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
fabrication_blocked  = true
```

未发送 `eth_sendTransaction` / `eth_sendRawTransaction`，未创建 signer。
