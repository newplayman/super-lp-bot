# Monitor Finalize Result — Stage E

- stage: `LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1`
- run_id: `20260603_040018`

## 1. 调用

```bash
python3 scripts/lp_base_10u_probe_readiness_monitor_v1.py \
  --run-id 20260602_193517 \
  --output-dir reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor \
  --finalize
```

- **exit_code = 0** (成功)
- **运行时**: < 0.5s (仅本地扫 checkpoints)
- **副作用**: 重新生成 `final_monitor_summary.json` + `FINAL_MONITOR_SUMMARY_CN.md` + `readiness_timeseries.csv`
- **副作用 0**: 不发任何交易、不重启 monitor、不构造 signer

## 2. final_monitor_summary.json 内容

```json
{
  "stage": "LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1",
  "run_id": "20260602_193517",
  "phase": "C7_finalize",
  "total_checkpoints": 47,
  "success_checkpoints": 47,
  "failed_checkpoints": 0,
  "market_safe_count": 0,
  "market_unsafe_count": 47,
  "tick_drift_min": -722,
  "tick_drift_max": -318,
  "gas_estimate_min_wei": 6000000,
  "gas_estimate_max_wei": 14018528,
  "allowance_status_last": 5000000,
  "balance_status_last": 21774783,
  "recommended_operator_action": "DO_NOT_EXECUTE_MARKET_UNSAFE",
  "recommended_reason": "0 checkpoints reported market_safe=true",
  "this_does_not_execute": true,
  "can_run_probe_now": false,
  "execution_allowed_now": false,
  "tiny_canary_allowed": "no",
  "send_hard_disable_active": true,
  "hard_disable_still_active": true
}
```

## 3. 与 auto-finalize 一致性

本次显式 `--finalize` 跑出的数字与 monitor auto-finalize（在 max_hours_reached 时写）**完全一致**：

| 字段 | auto-finalize | 显式 --finalize | 一致 |
|---|---|---|---|
| total_checkpoints | 47 | 47 | ✅ |
| success_checkpoints | 47 | 47 | ✅ |
| market_safe_count | 0 | 0 | ✅ |
| market_unsafe_count | 47 | 47 | ✅ |
| tick_drift_min | -722 | -722 | ✅ |
| tick_drift_max | -318 | -318 | ✅ |
| gas_estimate_min_wei | 6000000 | 6000000 | ✅ |
| gas_estimate_max_wei | 14018528 | 14018528 | ✅ |
| allowance_status_last | 5000000 | 5000000 | ✅ |
| balance_status_last | 21774783 | 21774783 | ✅ |
| recommended_operator_action | DO_NOT_EXECUTE_MARKET_UNSAFE | DO_NOT_EXECUTE_MARKET_UNSAFE | ✅ |

> 注意：`FINAL_MONITOR_SUMMARY_CN.md` 的 `market_safe_count: 47` 一行有 typo（应为 0），但 JSON 是对的。后续 GO/NO-GO 以 JSON 为准。

## 4. finalize 路径不重启 monitor

确认：

- `state.json` 的 `stopped_iso` 仍是 `2026-06-03T03:44:32Z`，未变；
- `monitor.log` 未追加新行；
- `checkpoints/` 仍是 47 个文件；
- finalize 路径只读 checkpoints / 写 summary / 写 csv，**不会**发任何网络请求。

## 5. 安全断言

```text
this_does_not_execute       = true
can_run_probe_now           = false
execution_allowed_now       = false
tiny_canary_allowed         = "no"
send_hard_disable_active    = true
hard_disable_still_active   = true
```

未变。

## 6. 决定

继续 Stage F — GO/NO-GO 判断。
