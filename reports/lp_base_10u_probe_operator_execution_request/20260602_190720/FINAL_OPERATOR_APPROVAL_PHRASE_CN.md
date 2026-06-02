# Final Operator Approval Phrase (Armed-Runner Build)

- stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- phase: E
- run_id: `20260602_190720`

## 两条短语 — 用途完全不同；不要混用

### 1) Armed-Runner Build 短语（**短期** — 仅授权下一阶段构建）

```text
APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

- **用途**: 仅授权 `LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1` 阶段开始构建 armed runner（包括 unseal hard-disable 的源码层 commit）
- **不授权**: 任何 send；任何 tx 广播；任何 signer 构造
- **下一阶段接受**: yes（armed build runner 的 argparse 会接受此短语作为 build authorization）
- **本阶段接受**: **NO** — 当前 stage 没有 build runner
- **生效条件 (in 下一阶段)**:
  - exact phrase match
  - argparse `--mode build-armed-runner`（假定下一阶段的命名约定）
  - 操作员 explicit consent
  - 仍需 dry-run-only / no-send 默认 true

### 2) One-Shot Execution 短语（**长期** — 用于最终真实发 tx 时）

```text
APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT wallet=0xb05b2872ace4564ff247555b6f7b097d31f3d835 pool=0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38 notional=10 hold=15m
```

- **用途**: 在 `LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1` 阶段（armed runner 已 build + reviewed）作为执行授权
- **本阶段不接受**: NO — 即使是 armed runner build 阶段也不接受
- **生效条件 (in 真正执行阶段)**:
  - exact phrase match (参见上一轮 `FINAL_HUMAN_APPROVAL_TEMPLATE_CN.md`)
  - `--mode execute-guarded`
  - `--i-understand-this-sends-real-transactions`
  - dry-run-only / no-send 必须显式覆盖为 false
  - send hard-disable 必须已经被独立 commit 解除
  - 27 项 pre-execution gate 全通过

## 当前阶段不接受**任何**短语执行

```text
this_stage_approves_phrase_for_execution = false
this_stage_approves_phrase_for_build     = false  # 仅展示，不立即接受
this_stage_validates_any_phrase_input    = false
this_stage_writes_chain_state             = false
```

操作员若想 "选 A"，下一阶段才需要键入 build 短语；本阶段只 **展示** 短语供熟悉。

## 短语对比表

| 维度 | Armed-Build Phrase | One-Shot Execution Phrase |
|---|---|---|
| 前缀 | `APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER` | `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT` |
| 授权范围 | 构建 armed runner（含 hard-disable 解除） | 实际发 mint/approve/decrease/collect tx |
| 接受阶段 | `LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1` | `LP_BASE_10U_PROBE_FIRST_EXECUTION_RUN_V1` |
| 接受时间 | armed build 启动时 | 最终 execution 启动时 |
| 是否构造 signer | no | yes (armed runner 已构造，但仍受 3-gate + 2-default 控制) |
| 是否广播 tx | no | yes (经全部 gate 后) |
| 失败影响 | 仅 build 失败 | 真实资金损失 |
| wallet/pool/notional/hold cross-check | yes (相同 4 项) | yes (相同 4 项) |

## 危险词重审

armed-build phrase 须确保**不包含**触发现有 27 危险词的子串：
- `APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER` 含 `EXECUTION` (子串) 但 word boundary `\bEXECUTE\b` 不命中（因 EXECUTION 末尾接 N，仍是 word char）；与 one-shot phrase 同样安全。
- 其余子串 `APPROVE` / `BUILD` / `BASE` / `10U` / `LP` / `PROBE` / `RUNNER` / `wallet=` / `pool=` / `notional=10` / `hold=15m` 都不在危险词列表。
- 注意：`10U` 包含子串 "U" 但 `\b10U\b` ≠ `\b20U\b`（不命中 20U）。

下一阶段的 `parse_build_approval_phrase`（假定函数名）应复用现有 27 危险词列表 + 4 cross-check 逻辑。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
this_stage_accepts_phrase     = false
build_phrase_can_execute_tx   = false
execution_allowed_now         = false
hard_disable_still_active     = true
```
