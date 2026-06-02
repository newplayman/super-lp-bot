# Monitor Finalize Flow — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- finalize script: `scripts/lp_base_10u_probe_readiness_monitor_v1.py --finalize`
- finalize 路径: **完全只读**；不会发任何交易、不会构造 signer、不会重跑任何 checkpoint

## 1. finalize 时机

1. **正常路径** — monitor 跑满 `max_hours`（默认 8h），自动进入 finally 分支调 `_finalize()`，写 `final_monitor_summary.json` 与 `FINAL_MONITOR_SUMMARY_CN.md`。
2. **中断路径** — 操作员在 tmux 内 `Ctrl+C`（SIGINT）或 `tmux kill-session`（SIGTERM），`stop_flag` 置位，下一次循环结束进入 finally。
3. **明早显式 finalize 路径** — 操作员（或下一个 stage 的 Agent）在明早运行：

   ```bash
   python3 scripts/lp_base_10u_probe_readiness_monitor_v1.py \
     --run-id 20260602_193517 \
     --output-dir reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor \
     --finalize
   ```

   这只会扫 `monitor/checkpoints/*.json` 写 summary，不会重启 monitor，不会发任何交易。

## 2. final_monitor_summary.json 字段契约

```text
stage                              = LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1
run_id                             = 20260602_193517
phase                              = C7_finalize
total_checkpoints                  = (从 checkpoints 目录读)
success_checkpoints                = (chain_id_match=true 的 checkpoint 数)
failed_checkpoints                 = (含 'error' 字段或 '_error' 字段的 checkpoint 数)
market_safe_count                  = (market_safe_for_execution_candidate=true 数)
market_unsafe_count                = (market_safe_for_execution_candidate=false 数)
tick_drift_min                     = min over drift_ticks
tick_drift_max                     = max over drift_ticks
gas_estimate_min_wei               = min over gas_price_wei
gas_estimate_max_wei               = max over gas_price_wei
allowance_status_last              = 最后一个 checkpoint 的 usdc_allowance_raw
balance_status_last                = 最后一个 checkpoint 的 usdc_balance_raw
recommended_operator_action        ∈ {GO_TO_FINAL_EXECUTION_AUTHORIZATION,
                                       DO_NOT_EXECUTE_MARKET_UNSAFE,
                                       REFRESH_DRY_RUN,
                                       STOP}
recommended_reason                 = (string)
this_does_not_execute              = true
can_run_probe_now                  = false
execution_allowed_now              = false
tiny_canary_allowed                = "no"
send_hard_disable_active           = true
hard_disable_still_active          = true
```

## 3. recommended_operator_action 决策树

```text
if total_checkpoints == 0:
    action = STOP
    reason = "no checkpoints collected"

elif market_safe_count == 0:
    action = DO_NOT_EXECUTE_MARKET_UNSAFE
    reason = "0 checkpoints reported market_safe=true"

elif every checkpoint has fresh_approval_required=true:
    action = REFRESH_DRY_RUN
    reason = "USDC allowance < 10 USDC 持续 < 阈值, 需要先 dry-run 重新预热 allowance"

else:
    action = GO_TO_FINAL_EXECUTION_AUTHORIZATION
    reason = "市场条件可接受; 进入下一阶段 (仍 NOT auto-execute)"
```

## 4. 严正声明

> **即使** `recommended_operator_action = GO_TO_FINAL_EXECUTION_AUTHORIZATION`，
> **本阶段不自动执行**。明早用户必须在新一轮 prompt 显式启动
> `LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1` 才会推进。
> 在此之前：armed runner v1 `execute-armed` 仍然硬退出，
> v2 `ExecutionSendDisabledInImplementationBuildStage` 仍然 raise。

## 5. 与本阶段其他约束的一致性

```text
can_run_probe_now         = false (finalize 不动)
execution_allowed_now     = false (finalize 不动)
tiny_canary_allowed       = "no"  (finalize 不动)
send_hard_disable_active  = true  (finalize 不动)
hard_disable_still_active = true  (finalize 不动)
arm_runner_built          = true  (v1 文件已存在)
preflight_smoke_ran       = true  (Stage 4)
preflight_smoke_pass      = WARN  (Stage 4; market drifted)
monitor_started           = true  (本阶段启动)
```

## 6. 防止 finalize 误触发任何动作的代码机制

`monitor_v1.py: _finalize()` 只做三件事：
1. `csv_path.write_text(...)` — 写本地 CSV
2. `summary_path.write_text(...)` — 写本地 JSON
3. `(out_dir / "FINAL_MONITOR_SUMMARY_CN.md").write_text(cn)` — 写本地 markdown

无 `subprocess`，无 `requests.post`，无 `eth_call`，无 `Web3`，无 `Account.from_key`，无任何网络或链交互。
