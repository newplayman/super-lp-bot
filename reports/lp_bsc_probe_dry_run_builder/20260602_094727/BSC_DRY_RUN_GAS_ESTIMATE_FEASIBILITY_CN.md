# Dry-run Gas Estimate Feasibility

- stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: H

## 可行性

```text
can_estimate_without_wallet                  = false
needs_wallet_address_for_reliable_estimate   = true
this_round_calls_eth_estimateGas             = false
this_round_uses_static_conservative_gas_assumptions = true
```

### 为何需要 wallet 地址

- `eth_estimateGas(approve)` 在 `from=zero_address` 或 zero-balance 时常 revert（USDT/BEP-20 在部分 fork 中检查 `msg.sender` balance）
- `eth_estimateGas(mint)` 必须满足 `allowance >= amountXDesired` 和余额充足，否则模拟 revert 不返回 gas
- `eth_estimateGas(decreaseLiquidity/collect)` 必须 wallet 已持有 tokenId，无 wallet ⇒ 无 tokenId ⇒ 估算未定义

因此**可靠 gas 估算必须放到下一阶段** `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1`（用户提供 wallet 地址后做 eth_estimateGas）。

## 本轮使用的静态保守 gas units

| 操作 | gas units（保守上界） |
|---|---|
| approve | 50,000 |
| mint | **380,000** |
| increaseLiquidity | 200,000 |
| decreaseLiquidity | 180,000 |
| collect | 80,000 |
| burn (optional) | 30,000 |
| swap.exactInputSingle | 130,000 |
| approve revoke (value=0) | 30,000 |

### 来源说明

- Pancake V3 NPM.mint() 观测主网范围 250k-400k（取决于 tick 初始化）
- Pancake V3 NPM.decrease+collect() 观测 120k-200k
- ERC20.approve() 30k-50k (USDT 在 BSC 是标准 BEP-20)
- SwapRouter.exactInputSingle 100k-160k

## Round-trip 总 gas（2×approve + mint + decrease + collect + 2×revoke）

```text
50k + 50k + 380k + 180k + 80k + 30k + 30k + buffer ≈ 870k
(burn 可选 +30k)
```

## 4 个 gas_cost 场景（按 $676.96/WBNB）

| 场景 | gas_price | round-trip gas USD | 备注 |
|---|---|---|---|
| current_baseline_low_gas | 0.05 gwei | **$0.0294** | Phase D 实测当下 BSC 基线 |
| modest_congestion_5x | 0.25 gwei | $0.1472 | 中度拥堵 |
| high_congestion_20x | 1.0 gwei | $0.5890 | 重拥堵；触发 S2 stop |
| extreme_outlier_100x | 5.0 gwei | $2.9450 | 绝不可 mint；S2 auto-abort |

## 推荐 gas_price 上限（per-session ceiling）

```text
recommended_gas_price_ceiling_for_probe_gwei = 0.50
```

理由：0.5 gwei 让 round-trip gas <~$0.30，安全位于 $0.50 MtM stop (S10) 之下，且在 probe ~$1 最坏损失预算之内。超过 0.5 gwei 时 gas 一次性吃掉超过 1.6× 预期总成本 — 应放弃 probe，等低拥堵窗口再来。

## confidence = medium

理由：gas units 来自公开范围观察而非真实 `eth_estimateGas`。它们是保守上界；下一阶段用真实 wallet 估算会更准（通常低 10-30%）。**medium** 反映的是没用 wallet 地址，不是模型本身有问题。

## 下一阶段必须做

1. `eth_estimateGas(from=wallet)` for approve(USDT) / approve(WBNB) / mint / decreaseLiquidity / collect / 2× revoke
2. 把每个估算和本文档保守上界比；超过的标出请人工 review
3. `eth_gasPrice` 拿当前 gas_price，校验 < per-session ceiling
4. probe 提交前算 `total_gas_cost_usd`，再次让 operator 确认

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
```
