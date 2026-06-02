# Gas 估计 + 可行性

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: J
- run_id: `20260602_112400`
- chain: Base (chain_id 8453)
- wallet_address_masked: `0xb05b...d835`

## Block / Gas snapshot

| 字段 | 值 |
|---|---|
| block_number | 46807927 |
| gas_price_observed_wei | 14,789,648 (0.01479 gwei) |
| gas_price_used_wei | 14,789,648 |
| base_fee_per_gas_wei | 13,789,648 (0.01379 gwei) |
| WETH USD anchor | $1,973.88 |

## eth_estimateGas 结果

| notional | call | 估计 gas | cost (ETH) | cost (USD) | read_success |
|---|---|---|---|---|---|
| 10U | `approve(USDC, 10e6)` | **38,704** | 5.72e-7 | $0.00113 | ✓ |
| 10U | `mint(0 WETH + 10 USDC)` | revert | — | — | ✗ (live revert) |
| 20U | `approve(USDC, 20e6)` | **38,704** | 5.72e-7 | $0.00113 | ✓ |
| 20U | `mint(0 WETH + 20 USDC)` | revert | — | — | ✗ (live revert) |

## Mint 估计 revert 解释

`eth_estimateGas` 在 publicnode 上对 `mint` 调用 **所有 amount0/amount1 组合都 revert**（测试过 amount0 ∈ {0, 1, 1e10, 1e14}, amount1 ∈ {4M, 5M, 10M, 20M}）。可能原因：
1. publicnode 节点在 estimateGas 时对 pool state 的快照与 `latest` 视图不一致（已知 publicnode tier 限制）
2. pool 流动性在 estimateGas 模拟期间被另一个 tx 改动

**fabrication_blocked = true**：不构造、不重试、不回退到非标准 selector。Mint gas 改用 **upstream 继承**：

| 来源 | `reports/lp_real_cost_model/20260601_141103/real_cost_model_results.csv` |
|---|---|
| pool | `0x72ab388e...` (WETH/USDC 0.01%) |
| scenario | `diagnostic_low` |
| mint_gas_units | **180,000** |
| 同一 chain (Base) | ✓ |

## 总 gas（approve + inherited mint）

| notional | approve gas | mint gas (inherited) | total gas | cost (ETH) | cost (USD) |
|---|---|---|---|---|---|
| 10U | 38,704 | 180,000 | **218,704** | 3.85e-6 | **$0.0076** |
| 20U | 38,704 | 180,000 | **218,704** | 3.85e-6 | **$0.0076** |

## 钱包 gas 可行性

| 字段 | 值 |
|---|---|
| wallet_eth_balance | 9.05e-5 ETH = $0.179 |
| 10U round-trip cost (approve+mint only) | $0.0076 |
| **feasibility 10U** | **✓**（24x margin on approve+mint alone） |

### Full round-trip 预估（out of scope for this stage）

| step | 预估 gas |
|---|---|
| approve USDC | 38,704 |
| mint | 180,000 (inherited) |
| decreaseLiquidity | ~150,000 (inherited from real_cost_model `decrease_liquidity_gas_units`) |
| collect | ~70,000 (inherited) |
| approve USDC revoke | 38,704 |
| **full round-trip total** | **~477,408** gas ≈ **$0.014** at current gas price |

`gas_feasible_10U_full_round_trip = ($0.014 < $0.18) = true`
`gas_feasible_20U_full_round_trip = ($0.014 < $0.18) = true`

> **结论：钱包 gas 余额足以跑 10U/20U 完整 round-trip 一次（甚至 12 次）**。但 **advisory**：在 0.014 gwei 极低 gas 价下 round-trip ≈ $0.014；gas 价短期上涨到 0.1 gwei 时涨到 ≈ $0.10，仍可覆盖；**超过 0.2 gwei** 则 USDC 钱包可能不够 buffer。**用户在签名 stage 需自行判断**。

## 已用 RPC（read-only）

- `eth_chainId`
- `eth_blockNumber`
- `eth_gasPrice`
- `eth_getBlockByNumber(latest, false)` （取 baseFeePerGas）
- `eth_estimateGas` × 4（2 approve + 2 mint；mint reverts）
- `eth_getBalance`

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
fabrication_blocked  = true (mint gas inherited, not fabricated)
```

未发送 `eth_sendTransaction` / `eth_sendRawTransaction`，未签名。
