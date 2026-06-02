# Stop Condition Engine Spec

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- phase: H
- run_id: `20260602_135824`

## 评估输入

`run_preflight()` 输出的 preflight dict。

## 13 个 stop（在 build stage 评估）

| id | 触发条件 | handling |
|---|---|---|
| stop_chain_id_mismatch | chain_id_observed != 8453 | abort_before_entry |
| stop_gas_balance_below_threshold | eth_balance_wei < 9.0e-5 ETH | abort_before_entry |
| stop_usdc_balance_below_required | usdc_balance_raw < 12e6 | abort_before_entry |
| stop_weth_balance_below_required | weth_balance_raw < 0 (数学上不可能；guard) | abort_before_entry |
| stop_allowance_unexpected (USDC) | usdc_allowance_raw > 50_000_000 | manual_intervention_required |
| stop_allowance_unexpected (WETH) | weth_allowance_wei > 1e24 | manual_intervention_required |
| stop_tick_moved_outside_planned_range_before_entry | abs(current_tick - (-200443)) > 200 | manual_intervention_required |
| stop_pool_liquidity_drop | current_liquidity < 1e15 | abort_before_entry |
| stop_gas_estimate_too_high | mint_estimate_gas <= 0 OR > 360_000 | abort_before_entry |
| stop_quoter_v2_failure | QuoterV2 返回 0 或 revert | abort_before_entry |
| stop_quote_slippage_above_threshold | slippage_pct > 5.0% | abort_before_entry |
| stop_rpc_instability | RPC 多次 timeout / 5xx / rate-limit | manual_intervention_required |
| stop_unknown_error | 任何未处理异常 | manual_intervention_required |

## 输出

```text
preflight.stop_conditions = {
  "stops": {stop_id: {triggered, handling, reason}, ...},
  "any_triggered": bool,
  "overall_status": "PASS" | "WARN" | "FAIL"
}
preflight.preflight_status = overall_status
```

| 情形 | preflight_status |
|---|---|
| 任意 stop_triggered with handling="abort_before_entry" | **FAIL** |
| 任意 stop_triggered with handling="manual_intervention_required" | **WARN** |
| 都没触发 | **PASS** |

## 硬性保证

```text
any_hard_stop_blocks_execution = true
warnings_do_not_become_execution = true
no_auto_retry                 = true
no_auto_execution              = true
```

## 安全

```text
wallet_or_tx_touched = false
```
