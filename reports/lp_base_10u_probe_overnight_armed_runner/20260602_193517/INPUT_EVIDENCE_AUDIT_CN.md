# Input Evidence Audit — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- branch: `feat/supabase-postgres-deployment`
- previous head: `f578e4a` (research: request base 10u probe operator decision 20260602_190720)
- previous stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- previous status: **PASS**
- operator choice this round: **A: APPROVE_BUILD_EXECUTION_RUNNER**

## 1. 本轮输入证据一览

| 序号 | 路径 | 关键字段 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/FINAL_VERDICT.json` | `status=PASS`, `recommended_next_stage=WAIT_FOR_OPERATOR_DECISION`, `allowed_next_stages=[WAIT_FOR_OPERATOR_DECISION, LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1, LP_BASE_10U_PROBE_EXECUTION_AUTHORIZATION_PACKAGE_FIX_REPEAT, STOP_LP_RESEARCH_NOW]` | OK |
| 2 | `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/OPERATOR_DECISION_MENU_CN.md` | A/B/C 三选项；`direct_execute_option_present=false`；A 路由到 `LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1` | OK |
| 3 | `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/operator_decision_menu.json` | `total_options=3`，`is_execution_authorization=false` 对所有三项 | OK |
| 4 | `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/FINAL_OPERATOR_APPROVAL_PHRASE_CN.md` | build phrase `APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER wallet=…` 显式只授权 build；不授权 send | OK |
| 5 | `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/final_operator_approval_phrase.json` | build phrase 与 one-shot phrase 前缀完全不同；`this_stage_accepts_no_phrase` 全 false | OK |
| 6 | `reports/lp_base_10u_probe_execution_authorization_package/20260602_184806/FINAL_VERDICT.json` | `status=PASS`，3 个 prior deviation 已 landed；`can_run_probe_now=false`，`hard_disable_still_active=true` | OK |
| 7 | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/FINAL_VERDICT.json` | `executor_v2_reviewed=true`，`execute_guarded_send_blocked=true`，`current_tick=-200747`，`tick_drift_observed=-304` | OK |
| 8 | `reports/lp_base_10u_probe_execution_implementation/20260602_163036/FINAL_VERDICT.json` | v2 build 完成；`executor_will_run_this_round=false`，`send_hard_disabled=true`，15 flags 全部 false | OK |
| 9 | `scripts/lp_base_10u_probe_executor_v2.py` | 992 lines；`ExecutionSendDisabledInImplementationBuildStage` 在 line 141 定义、line 974 raise；`--mode execute-guarded` 在 line 974 abort；本轮不修改 | OK |

## 2. 关键安全不变式（来自上游）

```text
can_run_probe_now         = false
execution_allowed_now     = false
hard_disable_still_active = true
edge_proven               = no
tiny_canary_allowed       = no
actual_fee_ready          = false
token_id_available        = false
wallet_or_tx_touched      = false
manual_approval_required  = true
operator_choice_recorded  = true_this_run
```

## 3. 操作员选择确认

本轮 prompt 操作员在 `feat/supabase-postgres-deployment` 启动了一个 stage 名为 `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`，并显式说明：

- 本选择 = **A: APPROVE_BUILD_EXECUTION_RUNNER**
- 本选择**只允许**：构建 armed runner；启动 8–10 小时只读 monitor
- 本选择**不允许**：执行 probe；发送交易；加载私钥；构造 signer；approve / mint / collect / swap
- 本选择**不允许**：花测试钱包资金

> A 选项的 `is_execution_authorization = false`（上游 decision menu 已确认）。

## 4. 本轮允许 vs 禁止

| 允许 | 禁止 |
|---|---|
| 构建 armed runner 代码 | 发送 eth_sendTransaction |
| 构建审批 parser | 发送 eth_sendRawTransaction |
| 构建 send path 但默认 disabled | 读私钥/助记词/keystore |
| 构建 signer path stub 但不得调用 | 构造 signer / wallet client |
| 构建 transaction send wrapper 必须 hard gated | 真实 approve / mint / decreaseLiquidity / collect / burn / swap |
| 构建 telemetry writer | 启动 live / paper / canary |
| 构建 abort/stop engine | 写 production positions |
| 构建 emergency no-send mode | 覆盖 shadow 原始表 |
| 构建 8–10 小时只读 monitor | 修改策略自动交易路径 |
| eth_call / staticcall / eth_getBalance | 自动 bridge / 自动换币 |
| ERC20 balanceOf / allowance | 花任何资金 |
| QuoterV2 staticcall | `can_run_probe_now` 设为 true |
| slot0 / liquidity / tickSpacing 读取 | `tiny_canary_allowed` 设为 yes |
| eth_estimateGas（仅在无签/无发的情况下） | 解除 send hard-disable |
| 写 reports / JSON / CSV / logs / checkpoint | 接受 one-shot execution phrase 视为有效 |
| commit / push |  |

## 5. 关键设计约束（armed runner v1）

1. **不修改 v2**：armed runner v1 通过 `import` 调用 v2 函数；v2 的 `ExecutionSendDisabledInImplementationBuildStage` raise 行为原样保留。
2. **本轮不 unseat hard-disable**：spec 上游 `commit_convention.commit_1_unseal` 仅在下一阶段（`LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1`）才执行；本阶段仍然停在 `OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`。
3. **`--mode execute-armed` 在本阶段必须 abort**：即使所有外部条件达成，armed runner v1 的 `execute-armed` 路径在本阶段也必须立即 abort，输出 `EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE` 错误并退出非零。
4. **monitor 是只读**：monitor 每 10 分钟一次，**只**调用 read-only RPC（eth_chainId、eth_blockNumber、eth_call(slot0/tickSpacing/liquidity)、eth_getBalance、eth_call(balanceOf/allowance)、eth_estimateGas 仅在无签/无发的 path）。

## 6. 状态切换

| 字段 | 本轮终值 | 说明 |
|---|---|---|
| `armed_runner_built` | `true` | v1 文件已写，但行为已限制为 no-send |
| `send_hard_disable_still_active` | `true` | v2 line 974 raise 保留；armed runner v1 的 execute-armed 在本阶段 abort |
| `default_no_send` | `true` | armed runner v1 默认 `--no-send` |
| `execute_armed_cannot_send_this_stage` | `true` | 已固化在 armed runner v1 的 main() 早退检查 |
| `preflight_smoke_ran` | `true` | Stage 4 已运行 |
| `preflight_smoke_pass` | `(true 或 warn)` | 取决于实时市场 |
| `monitor_started` | `true` | tmux session 已启动 |
| `monitor_session_name` | `lp_base_10u_probe_readiness_monitor_<RUN_ID>` | |
| `monitor_output_dir` | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor` | |
| `can_run_probe_now` | **false** | |
| `execution_allowed_now` | **false** | |
| `wallet_or_tx_touched` | **false** | |
| `tiny_canary_allowed` | **no** | |
| `recommended_next_stage` | **`WAIT_FOR_MONITOR_COMPLETION`** | 明早回来 finalize |

## 7. 上游不再变

armed runner v1 **不修改** `scripts/lp_base_10u_probe_executor_v2.py`（line count 不变）；新代码写入 `scripts/lp_base_10u_probe_armed_runner_v1.py`。monitor 脚本写入 `scripts/lp_base_10u_probe_readiness_monitor_v1.py`。
