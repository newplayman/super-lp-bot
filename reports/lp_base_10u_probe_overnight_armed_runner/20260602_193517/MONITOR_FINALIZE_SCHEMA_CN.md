# Monitor Finalize Schema — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

> 详细决策树与流程见 `MONITOR_FINALIZE_FLOW_CN.md`。本文档只固化 schema 契约。

## 1. monitor 跑完/被打断时自动写

```text
<output_dir>/final_monitor_summary.json     # 机器可读
<output_dir>/FINAL_MONITOR_SUMMARY_CN.md   # 人可读
<output_dir>/readiness_timeseries.csv      # 全 checkpoint 时序
```

## 2. final_monitor_summary.json 字段 schema

| key | type | 必填 | 说明 |
|---|---|---|---|
| stage | str | ✓ | "LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1" |
| run_id | str | ✓ | 时间戳目录名 |
| phase | str | ✓ | "C7_finalize" |
| total_checkpoints | int | ✓ | 检查点总数 |
| success_checkpoints | int | ✓ | chain_id_match=true 且无 error 字段 |
| failed_checkpoints | int | ✓ | 含 error 字段的检查点数 |
| market_safe_count | int | ✓ | market_safe_for_execution_candidate=true |
| market_unsafe_count | int | ✓ | market_safe_for_execution_candidate=false |
| tick_drift_min | int\|null | ✓ | drift_ticks 最小值 |
| tick_drift_max | int\|null | ✓ | drift_ticks 最大值 |
| gas_estimate_min_wei | int\|null | ✓ | gas_price_wei 最小 |
| gas_estimate_max_wei | int\|null | ✓ | gas_price_wei 最大 |
| allowance_status_last | int\|null | ✓ | 最后 usdc_allowance_raw |
| balance_status_last | int\|null | ✓ | 最后 usdc_balance_raw |
| recommended_operator_action | str | ✓ | GO_TO_FINAL_EXECUTION_AUTHORIZATION / DO_NOT_EXECUTE_MARKET_UNSAFE / REFRESH_DRY_RUN / STOP |
| recommended_reason | str | ✓ | 文字理由 |
| this_does_not_execute | bool | ✓ | **恒为 true** |
| can_run_probe_now | bool | ✓ | **恒为 false** |
| execution_allowed_now | bool | ✓ | **恒为 false** |
| tiny_canary_allowed | str | ✓ | **恒为 "no"** |
| send_hard_disable_active | bool | ✓ | **恒为 true** |
| hard_disable_still_active | bool | ✓ | **恒为 true** |

## 3. 决策树

```text
total_checkpoints == 0       -> STOP
market_safe_count == 0       -> DO_NOT_EXECUTE_MARKET_UNSAFE
all fresh_approval_required  -> REFRESH_DRY_RUN
otherwise                    -> GO_TO_FINAL_EXECUTION_AUTHORIZATION
```

## 4. 即使 GO_TO_FINAL_EXECUTION_AUTHORIZATION 也不自动执行

FINAL_MONITOR_SUMMARY_CN.md 文档必须包含以下字面段落：

> "Even if recommended_operator_action = GO_TO_FINAL_EXECUTION_AUTHORIZATION,
> this stage does NOT auto-execute. The user must explicitly request
> LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1 in the next prompt."
