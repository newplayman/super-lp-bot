# Runtime Self-Check Final Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: H
- run_id: `20260602_182402`
- 执行模式: 4 个 mode 顺序验证（preflight / print-unsigned / validate-approval / execute-guarded）。
- **所有调用都加 `--dry-run-only --no-send`；脚本默认值也是 true**。

## 调用 #1 — `preflight`

```bash
python3 scripts/lp_base_10u_probe_executor_v2.py \
  --mode preflight \
  --run-id 20260602_182402 \
  --wallet 0xb05b2872ace4564ff247555b6f7b097d31f3d835 \
  --notional 10 --hold 15m \
  --dry-run-only --no-send
```

- exit code: **0**
- chain_id_observed: 8453 (match expected)
- current_tick: **-200747** (drift -304 from frozen -200443)
- proposed_tick_lower / upper: **-200947 / -200547**
- current_tick_inside_new_range: **true**
- fresh_approval_required: **true**
- abort_reason: drift exceeds threshold
- no_send: true / dry_run_only: true
- 写入 7 个 telemetry artifact 占位 + dynamic_range.json 完整数据
- **transaction sent**: **NO**

## 调用 #2 — `print-unsigned`

```bash
python3 scripts/lp_base_10u_probe_executor_v2.py \
  --mode print-unsigned \
  --run-id 20260602_182402 \
  --wallet 0xb05b2872ace4564ff247555b6f7b097d31f3d835 \
  --notional 10 --hold 15m \
  --dry-run-only --no-send
```

- exit code: **0**
- candidate.tick_lower / upper: **-200962 / -200562**（注：这是另一次 fresh RPC read 的快照；drift 仍持续；范围由 print-unsigned 路径独立重算）
- unsigned_approve_package: amount_raw=10_000_000, approvemax_forbidden=true, no_send=true, transaction_sent=false
- unsigned_mint_package: deadline 1780428774 (now+3600), recipient=wallet, no_signature=true, no_send=true, transaction_sent=false
- `data` 字段以 `0x88316456...` 开头（mint selector 正确，非双 0x bug）
- **transaction sent**: **NO**

## 调用 #3 — `validate-approval`

```bash
python3 scripts/lp_base_10u_probe_executor_v2.py \
  --mode validate-approval \
  --run-id 20260602_182402 \
  --approval "APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m"
```

- exit code: **0**
- valid: **true**
- executes_now: **false**
- authorization_granted: **false**
- approval_phrase_effective_this_round: **false**
- execution_gates_status.gate_1_mode_execute_guarded: true
- execution_gates_status.gate_2_approval_phrase_exact_match: true
- execution_gates_status.gate_3_i_understand_this_sends_real_transactions: false（因未传该 flag）
- execution_gates_status.all_three_gates_pass: **false**
- execution_gates_status.send_would_be_authorized_now: **false**
- next_step_even_if_valid: `user_must_reapprove_at_final_execution_time_after_review_stage`
- **transaction sent**: **NO**

## 调用 #4 — `execute-guarded`（含 `--i-understand` 与不含两种）

调用 4a（**未传** `--i-understand-this-sends-real-transactions`）：

- exit code: **1**
- stderr: `EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE`
- **transaction sent**: **NO**

调用 4b（**已传** `--i-understand-this-sends-real-transactions`）：

- exit code: **1**
- stderr: `EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE`
- **transaction sent**: **NO**

两个调用都被 `raise ExecutionSendDisabledInImplementationBuildStage` 阻止，证明 send hard-disable 不依赖任何外部 flag。

## 关键事实

| 字段 | 值 |
|---|---|
| any_mode_sent_tx | **false** |
| execute_guarded_returncode | **1** (both with and without --i-understand) |
| execute_guarded_stderr_contains_EXECUTION_SEND_DISABLED | **true** |
| any_signer_constructed_during_self_check | **false** |
| any_wallet_client_constructed_during_self_check | **false** |
| any_private_key_loaded_during_self_check | **false** |
| read_only_rpc_used | **true** (eth_call slot0 + eth_chainId only) |
| telemetry_files_written | 7 (preflight / dynamic_tick_range / approval_check / unsigned_approve_package / unsigned_mint_package / stop_conditions / execution_gates) |
| telemetry_target_dir | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/` |
| production_db_written | **false** |
| shadow_table_written | **false** |
| positions_written | **false** |

## verdict

| field | value |
|---|---|
| preflight_ran_ok | true |
| print_unsigned_ran_ok | true |
| validate_approval_returned_valid_but_blocked | true |
| execute_guarded_blocked_send_returncode_1 | true |
| execute_guarded_blocked_send_with_i_understand | true |
| any_tx_send_attempted | false |
| runtime_self_check_pass | **true** |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched                  = false
can_run_probe_now                     = false
tiny_canary_allowed                   = no
any_tx_send_attempted                 = false
execute_guarded_send_blocked          = true
```
