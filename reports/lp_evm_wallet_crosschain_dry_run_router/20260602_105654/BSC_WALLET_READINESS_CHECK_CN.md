# BSC Wallet Readiness 检查

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- phase: F
- wallet_address_masked: `0xb05b...d835`

## BSC 候选（来自上一阶段 dry-run builder）

```text
pool         = 0x172fcd41e0913e95784454622d1c3724f546f849
pair         = USDT/WBNB
fee_tier_raw = 100  (0.01%)
preferred    = 10 USD
max          = 20 USD
```

## BSC 钱包实测余额（Phase D 已读）

| 资产 | USD |
|---|---|
| BNB (native) | **$0.00** |
| WBNB | $0.00 |
| USDT | $0.00 |
| USDC | $0.00 |
| BUSD | $0.00 |
| CAKE | (无 USD anchor) |
| **total** | **$0.00** |

## BSC 10U / 20U probe 所需

| 维度 | 10U | 20U |
|---|---|---|
| BNB gas balance min | ~$0.20（按 0.5 gwei 上限 × 870k units） | ~$0.20 |
| USDT 或 USDC token side | ~$5.0 | ~$10.0 |
| WBNB token side (≈ 0.0074 / 0.0148 WBNB) | ~$5.0 | ~$10.0 |
| **合计** | **~$10.20** | **~$20.20** |

## 判定

| 字段 | 结果 |
|---|---|
| bsc_gas_sufficient | **false** ($0.00) |
| bsc_usdt_sufficient_for_10u | **false** ($0.00) |
| bsc_wbnb_sufficient_for_10u | **false** ($0.00) |
| bsc_can_dry_run_10u | **false** |
| bsc_can_dry_run_20u | **false** |
| **bsc_candidate_blocked_by_funds_on_other_chain** | **true** |

证据：Base 端有 ≈ $26.84（ETH=$0.18 + WETH=$4.89 + USDC=$21.77）；BSC 端 = $0.00。
`likely_funded_chain = base`（Phase D 结论）。

## 本阶段**不**做的建议（按 brief 硬规定）

```text
× 不建议任何自动桥接
× 不建议任何自动换币
× 不推荐特定 bridge / DEX 切换方案
```

如果操作员未来希望恢复 BSC 候选：

> **由您自行决定**是否在 BSC 上准备 USDT + WBNB + BNB gas 余额。
> 资金获取路径（CEX 买入 + 提币到 BSC、或操作员自选 bridge）**在本 lpbot 工具范围之外**。
> 本阶段不会替您选 bridge，也不会替您发起任何 swap。

## 安全

```text
wallet_or_tx_touched                = false
can_run_probe_now                   = false
tiny_canary_allowed                 = no
edge_proven                         = no
no_bridge_suggestion_made           = true
no_swap_suggestion_made             = true
```
