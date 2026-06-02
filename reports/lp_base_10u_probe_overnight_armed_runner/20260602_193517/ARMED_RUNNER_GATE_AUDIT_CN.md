# Armed Runner Gate Audit — 14 项

- stage: `LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1`
- run_id: `20260602_193517`
- 范围：armed runner v1 未来进入 `execute-armed` 必须通过的 14 项 gate + 当前阶段已封的 5 项

## 1. 未来执行（armed runner v1 `execute-armed` 真要 unseat）必须 14 项全过

| # | Gate | 当前状态 | 未来 unseal 后状态 |
|---|---|---|---|
| 1 | 精确 build approval phrase（`APPROVE_BUILD_BASE_10U_PROBE_EXECUTION_RUNNER ...`） | **已实现 parser**（v2.parse_approval_phrase）但 build phrase 不通过 v2 正则（regex 为 one-shot 设计） | 未来 v3 应加 build phrase 的专门 regex 分支 |
| 2 | one-shot phrase 与 build phrase 前缀完全不同 | **已验证**（`is_build_phrase` ≠ `is_one_shot_phrase`） | 同 |
| 3 | notional = 10 USD | **已硬检查**（main() 早退 2） | 同 |
| 4 | hold = 15m | **已硬检查**（main() 早退 2） | 同 |
| 5 | wallet = `0xb05b2872ace4564ff247555b6f7b097d31f3d835` | **已硬检查**（main() 早退 2） | 同 |
| 6 | pool = `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` | **已硬检查**（armed runner v1 顶层常量；preflight 比对） | 同 |
| 7 | chain = Base（chain_id 8453） | **已硬检查**（preflight `chain_id_match`） | 同 |
| 8 | 需要 `--i-understand-this-sends-real-transactions` 第二确认 flag | **已实现**（argparse `store_true` 默认 False） | 同 |
| 9 | 运行时 fresh dynamic tick range（stop_conditions） | **已实现**（v2.dynamic_tick_range_recompute + stop_conditions 块） | 同 |
| 10 | 需要 stop condition 全清 | **已实现**（`any_stop_condition_active`） | 同 |
| 11 | 未来需要 `--no-send false` | **本阶段** `--no-send default=True`，**未来** unseal 阶段才可翻 | 同 |
| 12 | 未来需要 v2 hard-disable 已释放 | **本阶段** `SEND_HARD_DISABLE_ACTIVE=True`，**未来** unseal commit 才能 false | 同 |
| 13 | 当前阶段 send hard-disable = true | **true**（v2 line 974 raise 保留） | 仅在 unseal commit 后变 false |
| 14 | 当前阶段不能 execute | **true**（`mode_execute_armed` 硬退出，exit 1） | 下一阶段 unseal + i-understand + multi-gate 后才能 broadcast |

## 2. 本轮已封的 5 项

| Gate | 实际代码位置 | 状态 |
|---|---|---|
| armed runner v1 `execute-armed` 硬退出 | `mode_execute_armed` 返回 1，stderr 写 `EXECUTION_NOT_AUTHORIZED_IN_OVERNIGHT_BUILD_STAGE` | **封死** |
| 任何对 v2 的修改尝试都会让 v2 self-check 失败 | `_verify_v2_hard_disable_intact()` 在每次 `mode_status` 都重跑 | **封死** |
| one-shot phrase 被识别但**显式拒绝** | `mode_validate_approval` 设 `one_shot_accepted_in_this_stage: false` | **封死** |
| 默认 `--no-send True` / `--dry-run-only True` 不可被本阶段 CLI 翻 | argparse `action="store_true", default=True` | **封死** |
| 任何错误 wallet/notional/hold 在 dispatcher 前被 exit 2 | main() 顶层 3 项断言 | **封死** |

## 3. 与上游 spec 的对齐

上游 `next_stage_armed_runner_build_spec.json` 要求 armed runner build 阶段必须包含 10 项 objectives；本 armed runner v1 已覆盖其中 9 项（除了 `unseal_send_hard_disable`，因为本阶段是 `OVERNIGHT_…`，**故意** 不 unseal，留给下一阶段 `LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1`）。

| upstream objective | 本阶段是否覆盖 | 备注 |
|---|---|---|
| build_armed_runner | ✅ | v1 文件已写，6 mode 全部实现 |
| unseal_send_hard_disable | ❌（**故意留到下一阶段**） | 本阶段仍 `SEND_HARD_DISABLE_ACTIVE=true` |
| default_no_send | ✅ | argparse 默认 |
| still_requires_one_shot_phrase | ✅（v1 显式拒绝） | 未来 v3 才接受 |
| still_requires_i_understand_flag | ✅（argparse 已实现） | 未来真 unseal 路径必用 |
| abort_before_entry | ✅（v2 dynamic_tick_range + stop_conditions） | 复用 v2 |
| record_tokenId | ⏸（未在本 v1 实现，preflight 仅查 chain 状态） | 留给真 unseal 后 v3 阶段 |
| record_actual_fee | ⏸（同上） | 同上 |
| record_final_pnl | ⏸ | 同上 |
| emergency_stop | ⏸ | 同上 |

## 4. 已知偏移（写入 spec 的「future 必须有」清单）

1. v2 parse_approval_phrase 正则只识别 one-shot 形态。armed runner v1 接受任意合法形态，但显式标 `is_one_shot_phrase` / `is_build_phrase` 两个布尔。下一阶段（unseal 阶段）需要在 v3 中加入 build phrase 的专门 regex 分支或 hard-string equality 检查。
2. `mode_print_unsigned` 当前使用 v2 静态 tick `[-200643, -200243]` 占位；preflight mode 才用 dynamic range 覆盖。
3. armed runner v1 **没有**实现 `record_tokenId` / `record_actual_fee` / `record_final_pnl` / `emergency_stop`，因为这些必须真发交易后才能填值。unseal 阶段才补。

## 5. 与 CLAUDE.md 冻结的兼容性

- 不动 `internal/core/*`；
- 不动 `internal/adapters/*`；
- 不动 build-tag 入口；
- 不动 `cmd/lpbot/*`；
- 仅新增 read-only 路径的 Python 脚本与 Python 测试（与历史 `research:` commit 风格一致）。
