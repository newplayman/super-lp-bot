# Base 10U Probe Execution Implementation 总览

```text
stage                                       = LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1
run_id                                      = 20260602_163036
status                                      = PASS
previous_stage                              = LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1 (20260602_150957, commit 83b41b9)
previous_status                             = PASS

candidate_chain                             = Base (chain_id 8453)
candidate_pool                              = 0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38
candidate_pair                              = WETH/USDC
candidate_fee_tier                          = 100 (0.01%)
candidate_npm                               = 0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1
wallet                                      = 0xb05b2872ace4564ff247555b6f7b097d31f3d835
notional_usd                                = 10
hold_window                                 = 15m
tick range actually used                    = DYNAMIC (proposed this run: -200908 / -200508)
                                            = NOT legacy frozen -200643 / -200243

executor v2 script                          = scripts/lp_base_10u_probe_executor_v2.py (961 lines)
v1 preserved                                = scripts/lp_base_10u_probe_executor_v1.py (845 lines, unchanged since 9811257)

builder components
  executor_v2_built                         = true
  dynamic_tick_range_recompute_built        = true (reads slot0; computes proposed range from current tick)
  approve_exact_builder_built               = true (ApproveMax forbidden via UINT256_MAX//2 threshold)
  mint_tx_builder_built                     = true (deadline is now+3600; NOT legacy 2099-01-01 placeholder)
  exit_collect_revoke_builder_built         = true (monitor refuses iterations>1)
  telemetry_runtime_writer_built            = true (7 schema files; local-only)
  approval_gate_built                       = true (3 hard gates + 2 default safety flags)
  self_check_ran                            = true (5 cases all pass)
  execute_guarded_send_blocked              = true (EXITS 1 with EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE)

modes
  --mode preflight                          = dynamic_range read; PASS exit 0
  --mode print-unsigned                     = dynamic range used; unsigned_only/no_signature/no_send all true
  --mode validate-approval                  = valid=True but executes_now=False; 3-gate status
  --mode implementation-self-check          = 11-safety-flag summary; exit 0; no send triggered
  --mode execute-guarded                    = RAISES ExecutionSendDisabledInImplementationBuildStage; EXITS 1
                                            (even with --i-understand flag)

safety locks (all intact)
  can_run_probe_now                          = false
  can_execute_with_current_script            = false
  execution_ready_for_final_review           = false
  manual_approval_required_for_execution     = true
  executor_will_run_this_round               = false
  approval_phrase_effective_this_round       = false
  edge_proven                                = no
  actual_fee_ready                           = false
  token_id_available                         = false
  tiny_canary_allowed                        = no
  fabrication_blocked                        = true
  wallet_or_tx_touched                       = false

security audit (15 boolean safety flags) all PASS:
  private_key_loaded=false; mnemonic_loaded=false; keystore_loaded=false;
  signer_created=false; wallet_client_created=false;
  eth_sendTransaction_called=false; eth_sendRawTransaction_called=false;
  approve_executed=false; mint_executed=false; decrease_executed=false;
  collect_executed=false; burn_executed=false; swap_executed=false;
  can_run_probe_now=false; tiny_canary_allowed="no"

recommended_next_stage                      = LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1
                                              (review the implementation; STILL NOT execution; real send
                                               still requires fresh user approval at execution time after review)
```

## 一句话

实现 `scripts/lp_base_10u_probe_executor_v2.py` (961 lines) — 5 modes (preflight / print-unsigned / validate-approval / implementation-self-check / execute-guarded) + dynamic tick range recompute + approveExact builders + mint builder + exit/collect/revoke builders + 7-schema telemetry writer + 3-gate approval gate；**send 在本 stage 永远被 3 重门禁 + 2 default safety flag 包裹，`execute-guarded` 永远抛 `ExecutionSendDisabledInImplementationBuildStage` 退 1**；**15 项 boolean safety flag 全部 PASS**；v1 build-stage skeleton (845 lines) 保持不变；**未发送任何交易**；**未构造 signer**；**未加载任何私钥**。

## 严格禁区（本轮已遵守）

```text
× 未读私钥 / 助记词 / keystore
× 未创建 signer / wallet client
× 未调用 eth_sendTransaction / eth_sendRawTransaction
× 未真实 approve / mint / decreaseLiquidity / collect / burn / swap
× 未启动 live / canary / paper
× 未自动 bridge / swap
× 未写 production positions
× 未覆盖 shadow 原始表
× 未修改策略执行路径
× 未执行真实 probe
× 未修改 build-stage v1 脚本
× 未把审批短语作为本轮可执行短语接受
× 即将发生的 send 永远被 hard-disabled
```

## 偏离（deviation）声明

1. **encode_mint 产生双 0x 前缀**（本轮发现并修复）— 旧实现输出 `0x0x88316456...`；修复后正确以 `0x88316456` 开头，length 778。
2. **build_revoke_usdc_tx(0) 不能用 build_approve_exact_usdc_tx**（后者要求 amount>0）— 拆出 `_build_approve_tx_generic` helper；revoke 用 amount=0 走 generic 路径。
3. **tick drift 持续累积**（53 ticks in 13 min, 46 ticks in 30 min, 265 ticks in 30+ min）— v2 不直接用 frozen range；在 runtime 重算并 fresh_approval_required。

## 操作员后续抉择

```text
路径 A（推荐）：进入 LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1
              未来阶段会 review executor v2 脚本
              review 通过后仍需操作员在执行时点重新键入审批短语才会真正提交

路径 B：修改 implementation
              LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_FIX_REPEAT
              适合想换 gate / default / 监控策略 / 退出策略的人

路径 C：暂停 LP 研究
              recommended_next_stage = STOP_LP_RESEARCH_NOW
              所有 artifacts 完整保留可日后复用
```

## 安全门禁（本轮守住）

```text
wallet_or_tx_touched                  = false
can_run_probe_now                     = false
tiny_canary_allowed                   = no
edge_proven                           = no
fabrication_blocked                   = true
approval_phrase_effective_this_round  = false
executor_will_run_this_round          = false
execution_ready_for_final_review      = false
send_hard_disabled_in_this_stage      = true
```
