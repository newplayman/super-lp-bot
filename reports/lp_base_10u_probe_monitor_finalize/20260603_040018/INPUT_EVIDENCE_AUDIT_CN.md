# Input Evidence Audit — LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1

- stage: `LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1`
- run_id: `20260603_040018`
- branch: `feat/supabase-postgres-deployment`
- head before: `4550b5f` (research: build base 10u armed runner and start monitor 20260602_193517)
- source monitor run_id: `20260602_193517`

## 1. 上游 inputs 一览

| 路径 | 状态 | 关键 |
|---|---|---|
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/FINAL_VERDICT.json` | OK | `status=RUNNING`, `can_run_probe_now=false`, `execution_allowed_now=false`, `tiny_canary_allowed="no"`, `send_hard_disable_still_active=true`, `monitor_first_checkpoint_seen=true` |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ONEPAGE_CN.md` | OK | upstream ONEPAGE 标识 armed runner 状态 + monitor 启动事实 |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/MONITOR_START_HEALTHCHECK_CN.md` | OK | 启动时 8/8 PASS；首 checkpoint block 46820056, tick -200828, drift -385 |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/state.json` | OK | `started_iso=2026-06-02T19:44:19Z`, `stopped_iso=2026-06-03T03:44:32Z`, `stopped_reason=max_hours_reached`, `last_tick=-201165`, `last_drift=-722`, `last_market_safe=false`, `degraded=false` |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/monitor.log` | OK (但被 .gitignore 排除) | 见 `MONITOR_PROCESS_STATUS_CN.md` 的引用 |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/readiness_timeseries.csv` | OK | 47 行（iter 1–47）；全部 `market_safe=False`；`drift_ticks` 从 -318 单调恶化至 -722 |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/checkpoints/` | OK | 47 个 JSON 文件 |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/final_monitor_summary.json` | OK (auto-written) | `total_checkpoints=47`, `success_checkpoints=47`, `failed_checkpoints=0`, `market_safe_count=0`, `market_unsafe_count=47`, `tick_drift_min=-722`, `tick_drift_max=-318`, `gas_estimate_min_wei=6000000`, `gas_estimate_max_wei=14018528`, `allowance_status_last=5000000`, `balance_status_last=21774783`, `recommended_operator_action=DO_NOT_EXECUTE_MARKET_UNSAFE` |
| `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/FINAL_MONITOR_SUMMARY_CN.md` | OK（存在；含已知 typo `market_safe_count: 47`，与 JSON 不一致；以 JSON 为准） | 文字版与 JSON 版基本一致；`recommended_operator_action=DO_NOT_EXECUTE_MARKET_UNSAFE` |

> 注：CN markdown 在 `market_safe_count: 47` 一行有 typo（应为 0）；以 `final_monitor_summary.json` 为准，因 JSON 是 `--finalize` 路径直接 dump。

## 2. 关键安全不变式（来自上游）

```text
can_run_probe_now         = false
execution_allowed_now     = false
tiny_canary_allowed       = "no"
send_hard_disable_active  = true
hard_disable_still_active = true
edge_proven               = "no"
actual_fee_ready          = false
token_id_available        = false
wallet_or_tx_touched      = false
private_key_loaded        = false
manual_approval_required  = true
```

## 3. 上一阶段确定状态

```text
previous stage            = LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1
previous status           = RUNNING (bootstrap; monitor 在跑)
previous run_id           = 20260602_193517
previous commit           = 4550b5f
```

## 4. 本轮目标（来自 operator prompt）

1. 收尾 monitor 并生成 GO/NO-GO；
2. **不**执行 probe；
3. **不**发送任何交易；
4. **不**构造任何 signer；
5. **不**解除 hard-disable；
6. **不**自动选 GO 即使 monitor 全绿；
7. 当前已知 `fresh_approval_required=true` + `tick_drift` 超阈值 → 默认应该是 **REFRESH_REQUIRED** 或 **NO_GO**，不得强行 GO。

## 5. 已知 monitor 数据偏差

| 字段 | 取值 | 评估 |
|---|---|---|
| total_checkpoints | 47 | 47 次中 0 次 market_safe |
| success_checkpoints | 47 | RPC 全成功 |
| failed_checkpoints | 0 | 无失败 |
| market_safe_count | 0 | 0% — 长期不安全 |
| market_unsafe_count | 47 | 100% |
| tick_drift_min | -722 | 凌晨 03:34（最差）|
| tick_drift_max | -318 | 19:54 早段（最好）|
| gas_estimate_min_wei | 6000000 | 0.006 gwei (Base 极低) |
| gas_estimate_max_wei | 14018528 | 0.014 gwei |
| allowance_status_last | 5000000 (5 USDC) | 远 < 10 USDC 阈值 |
| balance_status_last | 21774783 (21.77 USDC) | 充裕 |
| recommended_operator_action | DO_NOT_EXECUTE_MARKET_UNSAFE | 与本阶段 GO/NO-GO 决策完全一致 |
| recommended_reason | "0 checkpoints reported market_safe=true" | |

## 6. 没有 missing 字段

- `state.json` ✅
- `monitor.log` ✅（在 .gitignore 中，但本地存在）
- `readiness_timeseries.csv` ✅
- `checkpoints/*.json` ✅ 47 个
- `final_monitor_summary.json` ✅
- `FINAL_MONITOR_SUMMARY_CN.md` ✅
- 上游 FINAL_VERDICT.json ✅
- 上游 ONEPAGE_CN.md ✅
- 上游 MONITOR_START_HEALTHCHECK_CN.md ✅

无伪造数据。

## 7. 决定

继续 Stage C — monitor 进程状态检查。
