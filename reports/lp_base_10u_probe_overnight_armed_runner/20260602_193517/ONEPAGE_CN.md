# Base 10U Probe — Overnight Armed Runner Build + Read-Only Monitor 总览

```text
stage                                       = LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1
run_id                                      = 20260602_193517
status                                      = RUNNING (monitor 在跑; verdict bootstrap 已发)
branch                                      = feat/supabase-postgres-deployment
head_before_start                           = f578e4a (LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1)
upstream_previous_stage                     = LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1 (PASS, 20260602_190720)
operator_choice                             = A_APPROVE_BUILD_EXECUTION_RUNNER
operator_choice_is_execution_authorization  = false

candidate
  chain                                     = Base (chain_id 8453)
  protocol                                  = Uniswap V3
  pool                                      = 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38
  pair                                      = WETH/USDC
  fee_tier                                  = 100
  npm                                       = 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1
  wallet                                    = 0xb05b2872ace4564ff247555b6f7b097d31f3d835
  notional                                  = 10 USD
  hold                                      = 15m

armed runner
  armed_runner_built                        = true
  armed_runner_file                         = scripts/lp_base_10u_probe_armed_runner_v1.py
  v2_modified                               = false
  v2_line_count_unchanged                   = true (992 lines)
  default_no_send                           = true
  default_dry_run_only                      = true
  send_hard_disable_still_active            = true (v2 line 974 raise 保留)
  execute_armed_cannot_send_this_stage      = true
  execute_armed_abort_message               = "EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE"
  execute_armed_exit_code                   = 1
  signer_path_not_called                    = true
  wallet_client_not_created                 = true

preflight (read-only, in-stage)
  preflight_smoke_ran                       = true
  preflight_smoke_pass                      = WARN
  preflight_smoke_reason                    = "fresh_approval_required=true; market drift -424 ticks from frozen center -200443 > 200 threshold"
  preflight_blocks_monitor                  = false

monitor (8-10h, in tmux)
  monitor_started                           = true
  monitor_session_name                      = lp_base_10u_probe_readiness_monitor_20260602_193517
  monitor_output_dir                        = reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor
  monitor_interval_minutes                  = 10
  monitor_max_hours                         = 8
  monitor_first_checkpoint_seen             = true
  monitor_first_checkpoint_iteration        = 1
  monitor_first_checkpoint_chain_id         = 8453
  monitor_first_checkpoint_block_number     = 46820056
  monitor_first_checkpoint_current_tick     = -200828
  monitor_first_checkpoint_drift_ticks      = -385
  monitor_first_checkpoint_market_safe      = false

safety locks (all intact)
  can_run_probe_now                          = false
  execution_allowed_now                      = false
  tiny_canary_allowed                        = no
  edge_proven                                = no
  actual_fee_ready                           = false
  token_id_available                         = false
  wallet_or_tx_touched                       = false
  hard_disable_still_active                  = true
  manual_approval_required                   = true
  private_key_loaded                         = false
  eth_sendTransaction_called                 = false
  eth_sendRawTransaction_called              = false
  approve_executed                           = false
  mint_executed                              = false
  decrease_executed                          = false
  collect_executed                           = false
  burn_executed                              = false
  swap_executed                              = false
  live_started                               = false
  canary_started                             = false
  paper_started                              = false
  any_funds_spent                            = false

recommended_next_stage                      = WAIT_FOR_MONITOR_COMPLETION
allowed_next_stages                         = WAIT_FOR_MONITOR_COMPLETION
                                              LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1
                                              LP_BASE_10U_PROBE_ARMED_RUNNER_BUILD_FIX_REPEAT
                                              STOP_LP_RESEARCH_NOW
```

## 一句话

armed runner v1 已 build（默认 no-send / dry-run-only / execute-armed 硬退出 1）；read-only preflight WARN（fresh_approval_required=true）；8h tmux monitor 已启动并产生第 1 个 checkpoint（block 46820056、tick -200828、drift -385、gas 14M wei）；**本阶段未发任何交易、未构造 signer、未解除 v2 hard-disable、未触碰 live/canary/paper、未花任何资金**；下一动作 = 等 monitor 跑满 8h 或明早用户回来 `--finalize`；**即使 monitor 明天全绿也不自动执行**。

## 阶段 9 验收（明早 monitor finalize 后再回填）

| 阶段 | 状态 |
|---|---|
| C1 INPUT_EVIDENCE_AUDIT | PASS |
| C2 ARMED_RUNNER_BUILD | PASS |
| C3 ARMED_RUNNER_GATE_AUDIT | PASS (14 future gates; 5 sealed this stage) |
| C4 ARMED_RUNNER_PREFLIGHT_SMOKE | WARN (fresh_approval_required=true; monitor continues) |
| C5 MONITOR_START | PASS |
| C6 MONITOR_START_HEALTHCHECK | PASS (8/8) |
| C7 MONITOR_FINALIZE_SCHEMA | PASS (schema + decision tree; --finalize tested) |
| C8 FINAL_VERDICT (bootstrap) | RUNNING |
| C9 test + safety scan | pending (committed in same commit) |
| C10 git publish | pending (this same commit) |

## 严格禁区（本轮已遵守）

```text
× 未读私钥 / 助记词 / keystore
× 未创建 signer / wallet client
× 未调用 eth_sendTransaction / eth_sendRawTransaction
× 未真实 approve / mint / decreaseLiquidity / collect / burn / swap
× 未启动 live / canary / paper
× 未自动 bridge / swap
× 未写 production DB / shadow 表 / positions
× 未修改 v2 executor 源码（line count 仍 992）
× 未把任何 approval phrase 当作立即执行授权
× send hard-disable 仍存在（未解除）
× monitor 只调用 read-only RPC（eth_chainId/eth_blockNumber/eth_call/eth_getBalance/eth_gasPrice）
× monitor 不持有任何 signer
```

## 后续操作

**今晚**：不用做任何事。monitor 在 tmux 内自跑，最多 8h。

**明早**：

```bash
# 1. monitor 状态
tail reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/monitor.log
cat reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/state.json

# 2. finalize 路径
python3 scripts/lp_base_10u_probe_readiness_monitor_v1.py \
  --run-id 20260602_193517 \
  --output-dir reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor \
  --finalize
cat reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/final_monitor_summary.json

# 3. 根据 recommended_operator_action 决定下一步:
#    * GO_TO_FINAL_EXECUTION_AUTHORIZATION -> 新一轮 prompt 启动
#       LP_BASE_10U_PROBE_FINAL_OPERATOR_AUTHORIZATION_REVIEW_V1
#    * DO_NOT_EXECUTE_MARKET_UNSAFE / REFRESH_DRY_RUN / STOP -> 不进入 armed build
```

> 即使 `recommended_operator_action = GO_TO_FINAL_EXECUTION_AUTHORIZATION`，
> **也**不自动执行 probe；操作员必须在新一轮 prompt 显式选下一步。
