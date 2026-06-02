# Approval Gate Final Review

- stage: `LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1`
- phase: E
- run_id: `20260602_182402`
- 审查源码: `scripts/lp_base_10u_probe_executor_v2.py`
  - `parse_approval_phrase` l.285-320
  - `execution_approval_gate` l.675-713
  - argparse 配置 l.831-849
  - 危险词列表 `DANGEROUS_WORD_PATTERNS` l.81-90
  - regex `APPROVAL_PHRASE_REGEX` l.77

## 未来唯一可能的执行审批短语

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

regex 限定为 `^APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0x[0-9a-fA-F]{40} pool=0x[0-9a-fA-F]{40} notional=10 hold=15m$`，仅 `wallet` / `pool` 的 40-hex 部分可变。

## 校验矩阵（基于源码 + 上一轮 4-test 已覆盖结果）

| # | 条件 | 期望结果 | 源代码定位 | 上一轮 test 结果 | 本阶段静态确认 |
|---|---|---|---|---|---|
| 1 | exact phrase only | regex `^...$` 强制 | l.77, l.296-298 | n/a | **PASS** |
| 2 | wrong wallet rejected | `parsed["wallet"] != WALLET` 返回 `valid:false` | l.310-311 | n/a | **PASS** |
| 3 | wrong pool rejected | `parsed["pool"] != POOL` 返回 `valid:false` | l.312-313 | n/a | **PASS** |
| 4 | notional=20 rejected | regex `notional=10` literal + `parsed["notional"] != 10` | l.77, l.314-315 | test_3 `20U_phrase_invalid` PASS rejected | **PASS** |
| 5 | hold=30m rejected | regex `hold=15m` literal + `parsed["hold"] != "15m"` + 危险词 `\b30M\b` `\b30m\b` | l.77, l.87, l.316-317 | n/a | **PASS** |
| 6 | dangerous words rejected | 27 patterns 包括 EXECUTE/EXEC/NOW/LIVE/CANARY/PAPER/MINT/SIGN/BURN/SWAP/BRIDGE/SEND/DEPLOY/GO/SHIP/PROCEED/20U/20u/30M/30m/USER_PROVIDED/USER_SELECTED/YES/EXECUTABLE/FUND/WITHDRAW/TRANSFER_OUT | l.81-90, l.292-294 | (上轮 implementation security audit covers) | **PASS** |
| 7 | approval phrase alone not enough | `execution_approval_gate` 还要求 `gate_1_mode_execute_guarded`、`gate_3_i_understand` | l.689, l.691, l.695 | test_2 `valid_phrase_no_i_understand` PASS blocks | **PASS** |
| 8 | 还需 second flag `--i-understand-this-sends-real-transactions` | argparse l.844, gate_3 = `i_understand_flag and second_flag_set_via_argv` | l.844, l.691 | test_2 PASS | **PASS** |
| 9 | 当前 stage 即使 phrase valid 也不会执行 | `--mode execute-guarded` 直接 raise (不依赖 gate 状态) | l.974-980 | implementation test PASS (returncode 1, EXECUTION_SEND_DISABLED stderr) | **PASS** |
| 10 | dry-run-only / no-send default true | argparse defaults | l.842-843 | implementation test PASS | **PASS** |

## 危险词 27 模式审查

模式：`\bEXECUTE\b`, `\bEXEC\b`, `\bNOW\b`, `\bLIVE\b`, `\bCANARY\b`, `\bPAPER\b`, `\bMINT\b`, `\bSIGN\b`, `\bBURN\b`, `\bSWAP\b`, `\bBRIDGE\b`, `\bSEND\b`, `\bDEPLOY\b`, `\bGO\b`, `\bSHIP\b`, `\bPROCEED\b`, `\b20U\b`, `\b20u\b`, `\b30M\b`, `\b30m\b`, `\bUSER_PROVIDED\b`, `\bUSER_SELECTED\b`, `\bYES\b`, `\bEXECUTABLE\b`, `\bFUND\b`, `\bWITHDRAW\b`, `\bTRANSFER_OUT\b`

**注意**：canonical phrase `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ...` 含 `EXECUTION` 子串但 **不含** `\bEXECUTE\b`（因为 `EXECUTION` 不在 word boundary `\bEXECUTE\b` 命中范围内 — `\bEXECUTE\b` 要求 `EXECUTE` 后接非单词字符，而 `EXECUTIO` 后接 `N`，仍是单词字符）。因此 `EXECUTION` 不会被误拒。这一点在源代码的注释 l.80 也有说明。

类似地：`PROBE`, `ONE_SHOT`, `APPROVE`, `BASE`, `LP`, `WALLET=`, `POOL=`, `NOTIONAL=10`, `HOLD=15m` 不在危险词列表里。

## 三重门禁验证（cross-reference）

| Gate | 实现 | 本 stage 行为 |
|---|---|---|
| Gate 1 — explicit `--mode execute-guarded` | argparse `choices` 强制 (l.834) | 即使 caller 写 `--mode execute-guarded`，l.974 raise |
| Gate 2 — approval phrase exact match | `parse_approval_phrase` (l.285) | 即使 phrase 正确，由于 Gate 1 仍 raise |
| Gate 3 — `--i-understand-this-sends-real-transactions` | argparse `store_true` (l.844) | 即使 flag 提供，由于 Gate 1 raise，整个组合永远阻断 |

## 当前 stage 行为确认

任意 `--mode execute-guarded` 调用：
1. argparse 解析（接受 mode）
2. forbidden env check（若环境干净通过）
3. 进入 `if args.mode == "execute-guarded":` 分支 (l.964)
4. 解析 gate2/gate3 状态（仅 logging 用途）
5. **直接** `raise ExecutionSendDisabledInImplementationBuildStage(...)` (l.974)
6. `__main__` `except` 捕获，`sys.exit(1)` (l.989-992)

无论 phrase 是否正确，无论 flag 是否提供，无论 dry-run-only/no-send 状态，结果都是 exit 1 + 不发任何交易。

## verdict

| field | value |
|---|---|
| exact_phrase_only | true |
| wrong_wallet_rejected | true |
| wrong_pool_rejected | true |
| notional_20_rejected | true |
| hold_30m_rejected | true |
| dangerous_words_rejected | true |
| approval_phrase_alone_not_enough | true |
| second_flag_required_future | true |
| current_stage_does_not_execute_even_if_valid | true |
| approval_gate_pass | **true** |

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
tiny_canary_allowed           = no
approval_phrase_effective_now = false
```
