# 输入证据审计

- stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
- run_id: `20260602_105654`
- 钱包地址（仅公开使用）：`0xb05b2872ace4564ff247555b6f7b097d31f3d835`

## BSC 侧上游（已读取）

| 字段 | 值 |
|---|---|
| dir | `reports/lp_bsc_probe_dry_run_builder/20260602_094727` |
| status | **`PASS`** |
| candidate_pool | `0x172fcd41e0913e95784454622d1c3724f546f849` (USDT/WBNB 0.01%) |
| preferred_notional_usd | 10 |
| max_notional_usd | 20 |
| can_run_probe_now | **false** |
| can_run_dry_run_with_wallet_address_next | **true** |
| upstream recommended_next_stage | `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1` |

## Base 侧上游（已读取）

| 数据层 | 关键事实 |
|---|---|
| **precise_quote** (`20260601_120001`) | 200 attempt / 120 succ / 80 fail；20U capacity_pass=24；high_confidence=57；db_ready=true |
| **v3_tick_liquidity_fix** (`20260601_132644`) | 5 selected v3 pool / 5 slot0_succ / 5 liquidity_avail / 5 high_conf；推荐下一阶段是 `LP_REAL_COST_MODEL_PIPELINE_V1` |
| **real_cost_model** (`20260601_141103`) | 5 pool / 5 cost_ready / 75 cost_usd_ready；6 positive_proxy_count_new；best_net_ev_proxy ≈ **+$0.038**；main blocker = `fee` |
| **real_fee_accrual** (`20260601_143401`) | 13 candidate / 13 pool_level_fee_ready / **0 actual_position_fee_ready**；blocker = `actual_position_fee_lineage_missing` |
| **universe_scope_audit** (`20260601_154136`) | normalized 池列表，多数行 reached_precise_quote=yes 但 reached_v3_tick_liquidity=no |

## 重要观察

1. **Base 已有 5 个 V3 池跑通 quote+tick+cost**，且有 6 个 positive proxy（new EV），best ≈ +$0.038。
2. **Base 与 BSC 同样的 `actual_position_fee_lineage_missing`** —— 都靠 pool-level fee proxy，actual 头寸 fee 还没在任何链上实测过。
3. `precise_quote_results.csv` 的 `amount_in_usd` / `amount_out_usd` 列有单位异常（cbBTC/USDC 行 `out_usd=3.4M` for `in_usd=20`），是上游 pipeline 的 known issue —— 本阶段路由判断不依赖这些 USD 列。
4. 用户声明"资金在 Base"必须通过本轮 read-only `eth_getBalance` 验证，不能假设。

## 本轮范围

```text
crosschain_wallet_address_dry_run_routing_only
```

不做：

- 加载私钥 / 助记词 / keystore
- 创建 signer / wallet client
- 发送 eth_sendTransaction / eth_sendRawTransaction
- 执行 approve / mint / decrease / collect / burn / swap
- 启动 live / canary / paper
- 自动桥接 / 自动换币
- 翻转 can_run_probe_now / tiny_canary_allowed
- 在 Base RPC 不可用时**编造** Base 余额数字

允许：

- eth_chainId / eth_blockNumber / eth_getBalance
- ERC20.balanceOf / ERC20.allowance（只读 eth_call）
- 从观察到的余额推算 likely_funded_chain
- 推荐 allowed-set 中的下一阶段名

## 通过

```text
all 18 inputs present       = yes
all upstream gates aligned  = yes
proceed_to_phase_C          = true
```
