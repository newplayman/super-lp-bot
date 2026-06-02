# 输入证据审计

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- phase: B
- run_id: `20260602_112400`
- 上一阶段: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1` (20260602_105654)
- 钱包地址（仅公开使用）: `0xb05b2872ace4564ff247555b6f7b097d31f3d835`

## 1. 上游门禁校验

| 门禁 | 期望 | 实际 | 通过 |
|---|---|---|---|
| 上一阶段 status | PASS | PASS | ✓ |
| likely_funded_chain | base | base | ✓ |
| base_total_usd_proxy | > 10 | 26.84 | ✓ |
| bsc_total_usd_proxy | 0 or near 0 | 0.00 | ✓ |
| base_dry_run_ready_candidate_count | ≥ 1 | 5 | ✓ |
| 上一阶段 recommended_next_stage | LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1 | LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1 | ✓ |
| 上一阶段 can_run_probe_now | false | false | ✓ |

## 2. 上游已读取 artifacts（14 项）

| 类别 | 路径 | 关键事实 |
|---|---|---|
| router FINAL_VERDICT | `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json` | status=PASS, primary=WETH/USDC 0x72ab388e..., can_run_probe_now=false |
| router base candidate | `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/base_candidate_from_existing_artifacts.json` | 5 pools / 5 ready, primary 双 token 命中 |
| router balance audit | `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/evm_wallet_crosschain_balance_audit.json` | base ETH=$0.18, WETH=$4.89, USDC=$21.77 |
| router balance CN | `.../EVM_WALLET_CROSSCHAIN_BALANCE_AUDIT_CN.md` | human-readable 余额审计 |
| router allowance audit | `.../evm_wallet_crosschain_allowance_audit.json` | uni_v3_npm_base WETH=0.00247 / USDC=5.0 |
| router allowance CN | `.../EVM_WALLET_CROSSCHAIN_ALLOWANCE_AUDIT_CN.md` | ApproveExact 旧痕迹说明 |
| router bsc readiness | `.../bsc_wallet_readiness_check.json` | bsc 0 资金，dry-run 不可 |
| router preflight next spec | `.../base_10_20u_probe_preflight_review_next_spec.json` | 本阶段 phase A-L 结构镜像 |
| precise_quote | `reports/lp_precise_quote/20260601_120001/precise_quote_results.csv` | primary 0x72ab388e 行存在, 20U capacity_pass |
| precise_quote verdict | `.../FINAL_VERDICT.json` | db_ready=true, recommended_next_stage=LP_V3_TICK_LIQUIDITY |
| v3_tick_liquidity | `reports/lp_v3_tick_liquidity_fix/20260601_132644/v3_tick_liquidity_v2_results.csv` | primary row: current_tick=-200503, current_liquidity=4.55e17 |
| v3_tick_liquidity verdict | `.../FINAL_VERDICT.json` | 5/5 pool snapshot PASS, high_conf=5 |
| real_cost_model | `reports/lp_real_cost_model/20260601_141103/real_cost_model_results.csv` | primary 0x72ab388e: total_cost_usd_20u=$0.038, quote_gas=203739 |
| real_fee_accrual | `reports/lp_real_fee_accrual/20260601_143401/real_fee_economics_preview.csv` | primary: new_net_ev_proxy=-$0.0600, fee_source=pool_level_proxy_only |

## 3. Primary 候选池交叉对齐

| 来源 | 0x72ab388e... 的事实 |
|---|---|
| router base_candidate | WETH/USDC, fee=100, wallet 双 token 命中, best_ev=-$0.0600, status=BASE_DRY_RUN_READY |
| precise_quote | 行存在, 20U capacity_pass |
| v3_tick_liquidity | slot0 / liquidity / ticks 完整, current_tick=-200503, liquidity=4.55e17 |
| real_cost_model | total_cost_usd_20u=$0.038, quote_gas=203739, confidence=low |
| real_fee_accrual | new_net_ev_proxy=-$0.0600, status=NEGATIVE_PROXY, fee_source=pool_level_proxy_only |

✓ 4 个数据层 primary pool 行均存在且 self-consistent（除 high_confidence 偏低 = upstream known issue）

## 4. 重要观察（从上游 carry-over）

1. **钱包 4 个 Base token 余额 0**：USDT, cbBTC, DAI（不影响 WETH/USDC 候选；WETH+USDC 双命中）
2. **Base gas balance $0.18** < 保守阈值 $0.20 — 差 $0.02；advisory only，下一阶段 `eth_estimateGas from=wallet` 才能给出真实判断
3. **Primary 池 best_ev_proxy=-$0.06** 与 BSC USDT/WBNB 0.01% 同档（-$0.0156），都是"通道验证而非 +EV 押注"
4. **fee_source=pool_level_fee_velocity_proxy_only** — `actual_position_fee_lineage_missing` 是 upstream blocker；本阶段不修，read-only dry run 不需要 lineage
5. **5 个候选里唯一微正 EV = VIRTUAL/WETH +$0.038**，但钱包不持 VIRTUAL；本阶段**绝**不替用户做 swap 换 VIRTUAL

## 5. 本轮范围

```text
base_10_20u_probe_dry_run_builder_only
```

### 允许

- `eth_chainId` / `eth_blockNumber` / `eth_getBalance` / `eth_call` (slot0 / liquidity / ticks / token0 / token1 / fee / tickSpacing)
- `ERC20.balanceOf` / `ERC20.allowance` (read-only)
- `QuoterV2.quoteExactInputSingle` (`from=wallet`, read-only)
- `eth_estimateGas` (`from=wallet`, read-only)
- 组装 wallet-bound unsigned tx package（recipient=wallet, deadline=placeholder, ApproveExact）
- 推荐下一阶段名（仅限 allowed-set）

### 禁止

- 加载私钥 / 助记词 / keystore
- 创建 signer / wallet client
- 发送 `eth_sendTransaction` / `eth_sendRawTransaction`
- 执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
- 启动 lpbot-live / lpbot-canary / lpbot-paper
- 自动桥接 / 自动换币
- 翻转 `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`
- 在 Base RPC 不可用时**编造** slot0 / liquidity / balance / allowance 数字

## 6. 通过

```text
all 14 inputs read         = yes
all upstream gates aligned = yes
proceed_to_phase_C         = true
wallet_or_tx_touched       = false
can_run_probe_now          = false
tiny_canary_allowed        = no
edge_proven                = no
```
