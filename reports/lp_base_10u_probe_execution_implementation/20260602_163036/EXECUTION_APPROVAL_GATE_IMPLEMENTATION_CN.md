# Execution Approval Gate 实现

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: I
- run_id: `20260602_163036`

## 实现

`scripts/lp_base_10u_probe_executor_v2.py` 中 `execution_approval_gate(phrase, dry_run_only, no_send, i_understand_flag, second_flag_set_via_argv)`。

## 未来审批短语

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

**仍不生效于本轮**。

## 校验

- approval phrase exact regex match
- whole-word dangerous-word check（27 patterns）
- cross-checks: wallet, pool, notional, hold

## 三重硬门禁

| gate | 描述 | 是否可绕过 |
|---|---|---|
| gate_1 | 显式 `--mode execute-guarded`（argparse choices 强制） | 不可 |
| gate_2 | 审批短语 regex 精确匹配（whole-word dangerous-word 过滤） | 不可 |
| gate_3 | `--i-understand-this-sends-real-transactions` 第二道 flag | 不可 |

## 两个 default safety flags

| flag | default | 含义 |
|---|---|---|
| `--dry-run-only` | **true** | 只构造 tx，不广播 |
| `--no-send` | **true** | 不发送任何 signed payload |

## 本 stage 硬性 send 禁用

**即使** 3 个 gate 全过 + 2 个 safety default 全 hold，`execute-guarded` mode **仍会** raise `ExecutionSendDisabledInImplementationBuildStage` + 退 1。**任何 send 都被本 stage 硬阻止**。

只有未来 `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1` 之后的下下阶段才允许 send。

## 4 项测试 全部 PASS

| # | test | result |
|---|---|---|
| 1 | valid phrase + all 3 gates + dry-run-only + no-send | **PASS** (all_three_gates_pass=True, send_would_be_authorized_now=True) |
| 2 | valid phrase but no `--i-understand` flag | **PASS** (gate_3=False, blocks send) |
| 3 | 20U phrase (invalid) | **PASS** (phrase_valid=False, regex mismatch) |
| 4 | valid phrase but `dry-run-only=False` | **PASS** (all_safety_defaults_hold=False, blocks send) |

## 安全

```text
wallet_or_tx_touched = false
can_run_probe_now    = false
tiny_canary_allowed  = no
send_hard_disabled_in_implementation_build_stage = true
```
