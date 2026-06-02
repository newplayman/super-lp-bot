# Next Stage Spec — Armed Runner Build (V1)

- stage: `LP_BASE_10U_PROBE_OPERATOR_EXECUTION_REQUEST_V1`
- phase: G
- run_id: `20260602_190720`
- **本草案描述未来阶段；当前 stage 不构建任何 runner**。

## 未来阶段名（仅在操作员选 A 后才进入）

```text
LP_BASE_10U_PROBE_EXECUTION_RUNNER_ARMED_BUILD_V1
```

## 阶段目标

1. **构建 armed runner** — 在新建脚本（提议命名 `scripts/lp_base_10u_probe_executor_v3_armed.py`）中实现可发送 tx 的版本，但是默认仍 no-send。
2. **解除 send hard-disable** — 在 armed runner 中**不再** raise `ExecutionSendDisabledInImplementationBuildStage`；改为根据 3-gate + 2-default + RPC 状态决定是否广播。**必须在独立 commit 中完成**（commit prefix `unseal:`）。
3. **仍默认 no-send** — `--dry-run-only` / `--no-send` argparse 默认 true；只有操作员显式覆盖才可能发送。
4. **仍需最终执行短语** — armed runner 内部 `parse_one_shot_execution_phrase` 校验 `APPROVE_BASE_10U_LP_PROBE_EXECUTION_ONE_SHOT ...` 完全匹配（复用现有 regex + 27 危险词 + 4 cross-check）。
5. **仍需 `--i-understand-this-sends-real-transactions`** — argparse store_true，必须显式传。
6. **必须支持 abort before entry** — 在 mint 之前任意 gate（preflight / dynamic_tick_range / quote / gas estimate / balance / allowance）失败立即 abort，无任何 partial state。
7. **必须记录 tokenId** — 复用 Stage F MINT_RECEIPT_TOKENID_SCHEMA；任何提取失败 ⇒ manual intervention。
8. **必须记录 actual fee** — 复用 Stage G ACTUAL_FEE_TELEMETRY_SCHEMA；entry/hold/pre_exit/post_collect 4 时间点；写不到 ⇒ `actual_fee_ready=false`。
9. **必须记录 final PnL** — 公式见上轮 BASE_10U_PROBE_AUTHORIZATION_SUMMARY。
10. **必须支持 emergency stop** — 操作员 SIGINT/SIGTERM ⇒ runner 必须：
    - 立即停止任何 in-flight tx broadcast
    - 不 panic，落盘 last-known telemetry
    - 标记 `emergency_stop=true`，进入 manual intervention（即使 mint 已成功，hold/exit 也必须人工接管）

## 阶段必须 **不** 做

| 不可以 | 原因 |
|---|---|
| × 接受 one-shot execution phrase | 该 phrase 在 `FIRST_EXECUTION_RUN_V1` 阶段才生效；armed build 阶段只接受 build phrase |
| × 发送任何 tx | armed build = 仅 build；默认 no-send |
| × 解除 dry-run-only / no-send 默认值 | 必须保持 true，由 caller 显式覆盖 |
| × 跳过 27 项 pre-execution checklist | 任何 gate 失败 abort |
| × 自动循环 | iterations = 1 only；与 v2 monitor 行为一致 |
| × 触碰 production DB / shadow tables / positions | telemetry 仅落 reports dir |
| × 修改策略执行路径（core/strategy） | 与 hexagonal 隔离原则一致 |
| × 跨链 bridge / 跨池 swap | 6-allow whitelist 严格执行 |

## 文件约定

| 路径 | 内容 |
|---|---|
| `scripts/lp_base_10u_probe_executor_v3_armed.py` | armed runner 主体；与 v2 共享常量；ImportError-safe |
| `scripts/lp_base_10u_probe_executor_v2.py` | **保持不变** — 仍带 hard-disable；作为 fallback / sanity reference |
| `tests/test_lp_base_10u_probe_executor_v3_armed_build_v1.py` | armed build 阶段测试；覆盖 no-send default、phrase 校验、abort 路径、emergency stop |
| `reports/lp_base_10u_probe_execution_runner_armed_build/<RUN_ID>/` | 该阶段所有 artifact 落地 |

## 必须新增的 telemetry schema

| schema | 落盘文件 | 用途 |
|---|---|---|
| `lp_probe_armed_runner_self_check_v1` | `armed_runner_self_check.json` | 启动时自检（gates、hard-disable status、env、cwd 等） |
| `lp_probe_armed_runner_build_phrase_check_v1` | `build_phrase_check.json` | build phrase 校验日志 |
| `lp_probe_armed_runner_dry_run_simulation_v1` | `dry_run_simulation.json` | dry-run-only 模式下模拟整个 9-step 序列 |

## commit / PR 约定

- armed build 阶段必须有 **至少 2 个独立 commit**：
  - `unseal: release send hard-disable for armed build (executor v3)` — 仅源码层解除，包含旧 raise 改 conditional dispatch 的 diff
  - `research: build armed runner scaffold + tests <RUN_ID>` — runner 主体与 telemetry
- PR description 必须含 `EXECUTION_HARD_DISABLE_RELEASE_AUDIT.md` 链接，第二审 reviewer 显式同意
- 解封 commit 单独可 revert（rollback safety）

## 当前阶段不执行

```text
this_stage_creates_armed_runner_file              = false
this_stage_modifies_executor_v2                    = false
this_stage_unseals_send_hard_disable               = false
this_stage_writes_any_commit_to_armed_runner_dir   = false
this_stage_only_writes_a_documentation_spec        = true
```

下一阶段（armed build）将根据此 spec 实现；本 spec 文档可在那阶段被 cite 并扩展。

## 安全（本阶段不变量）

```text
wallet_or_tx_touched          = false
can_run_probe_now             = false
execution_allowed_now         = false
hard_disable_still_active     = true
this_phase_is_doc_only        = true
```
