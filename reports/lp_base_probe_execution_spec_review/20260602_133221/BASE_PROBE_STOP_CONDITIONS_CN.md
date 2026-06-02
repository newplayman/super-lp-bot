# Base 10U Probe 硬性 Stop Conditions

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- phase: E
- run_id: `20260602_133221`

> 本文件定义未来真实执行时的硬性 stop 条件。本轮不触发任何 stop；只 design。

## 处理动作定义

| action | 含义 |
|---|---|
| `abort_before_entry` | 立即 halt；不提交任何 tx；写 `HALT_<reason>_CN.md`；要求新审批才能重试 |
| `exit_immediately` | 跳到 Step 4（decreaseLiquidity+collect+revoke）；不等待 hold_window |
| `manual_intervention_required` | halt；不自动 exit；报告操作员；不自动 retry；等操作员决定 |
| `do_not_retry_automatically` | 任何失败或 stop **绝不**自动 retry；retry 必须新审批 + 新 session_id |

## 全部 stop 条件（20 项）

| # | id | 阶段 | 条件 | handling |
|---|---|---|---|---|
| 1 | stop_chain_id_mismatch | Step 0 | eth_chainId != 8453 | abort_before_entry |
| 2 | stop_wallet_mismatch | Step 0 | 钱包公钥 hash/nonce 与 frozen 不一致 | abort_before_entry |
| 3 | stop_gas_balance_below_threshold | Step 0 | ETH balance < 9.0e-5 或 < 1.5x 总 gas | abort_before_entry |
| 4 | stop_usdc_balance_below_required | Step 0 | USDC < (notional + 2) | abort_before_entry |
| 5 | stop_weth_balance_below_required | Step 0 | guard against 0-WETH probe 被错配为 WETH-needed | abort_before_entry |
| 6 | stop_allowance_unexpected | Step 0 | USDC.allowance > 50M 或 WETH.allowance > 1e24 | manual_intervention_required |
| 7 | stop_quote_slippage_above_threshold | Step 0 | QuoterV2 out < 0.95 * expected | abort_before_entry |
| 8 | stop_tick_moved_outside_planned_range_before_entry | Step 0 | abs(tick - (-200443)) > 200 | manual_intervention_required |
| 9 | stop_pool_liquidity_drop | Step 0 | pool.liquidity < 1e15 或 < 10% frozen | abort_before_entry |
| 10 | stop_quoter_v2_failure | Step 0 | QuoterV2 revert 或返回 0 | abort_before_entry |
| 11 | stop_gas_estimate_too_high | Step 0 | mint estimateGas > 360k 或 revert | abort_before_entry |
| 12 | stop_approve_tx_pending_too_long | Step 1 | approve pending > 5min 或被替换或 nonce gap | manual_intervention_required |
| 13 | stop_approve_revert | Step 1 | approve tx revert | abort_before_entry |
| 14 | stop_mint_tx_pending_too_long | Step 2 | mint pending > 5min 或被替换或 nonce gap | manual_intervention_required |
| 15 | stop_mint_revert | Step 2 | mint tx revert (INSUFFICIENT_LIQUIDITY / INVALID_TICK_RANGE / ...) | exit_immediately |
| 16 | stop_token_id_not_found_after_mint | Step 2 | Transfer event 缺失 或 positions(tokenId)=0 | manual_intervention_required |
| 17 | stop_mtm_drawdown_beyond_threshold | Step 3 | mtm drawdown > 20% entry principal | exit_immediately |
| 18 | stop_tick_out_of_range_during_hold | Step 3 | tick 跳出 range 且 > 2min 未回 | exit_immediately |
| 19 | stop_exit_quote_unavailable | Step 4 | 关闭方向 QuoterV2 revert 或返回 0 | manual_intervention_required |
| 20 | stop_collect_failure | Step 4 | NPM.collect revert | manual_intervention_required |
| 21 | stop_rpc_instability | any | 连续 3 次 timeout/5xx/rate-limit | manual_intervention_required |
| 22 | stop_unknown_error | any | 任何上面未覆盖的异常 | manual_intervention_required |

## 自动 retry 政策

```text
no_auto_retry = true

任何失败或 stop 都不自动 retry。
任何 retry 必须：
  - 新审批短语
  - 新 session_id
  - 新 telemetry run_id
```

## 退出后处理

```text
1. 写 HALT_<reason>_CN.md (manual_intervention / abort_before_entry / exit_immediately 三类)
2. 写当前 phase + 触发条件 + 已发出的 tx hash (if any)
3. 已发的 approve 不需要专门撤销（invariant #10 强制在 Step 5 revoke；abort case 也走 revoke if possible）
4. 操作员决定 retry / abandon
```

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
edge_proven          = no
```
