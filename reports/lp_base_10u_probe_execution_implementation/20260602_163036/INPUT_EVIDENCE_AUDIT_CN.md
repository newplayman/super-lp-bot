# 输入证据审计

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- phase: B
- run_id: `20260602_163036`
- 上一阶段: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1` (20260602_150957, commit `83b41b9`)

## 1. 上游门禁校验

| 门禁 | 期望 | 实际 | 通过 |
|---|---|---|---|
| 上一阶段 status | PASS | PASS | ✓ |
| execution_implementation_allowed_next | true | true | ✓ |
| executor_script_reviewed | true | true | ✓ |
| static_security_pass | true | true | ✓ |
| mode_behavior_pass | true | true | ✓ |
| preflight_output_reviewed | true | true | ✓ |
| unsigned_package_reviewed | true | true | ✓ |
| approval_parser_reviewed | true | true | ✓ |
| execution_stubs_reviewed | true | true | ✓ |
| telemetry_schema_reviewed | true | true | ✓ |
| can_run_probe_now | false | false | ✓ |
| can_execute_with_current_script | false | false | ✓ |
| executor_will_run_this_round | false | false | ✓ |
| approval_phrase_effective_this_round | false | false | ✓ |
| edge_proven | no | no | ✓ |
| tiny_canary_allowed | no | no | ✓ |
| fabrication_blocked | true | true | ✓ |
| wallet_or_tx_touched | false | false | ✓ |
| recommended_next_stage | LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1 | LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1 | ✓ |
| v1 script unchanged since 9811257 | true | true | ✓ |

## 2. 上一阶段重要发现（必须在本轮处理）

| 项 | 值 |
|---|---|
| current_tick 漂移 | -200609 → -200662 (53 ticks in ~13 min) |
| cumulative drift from frozen -200443 | **219 ticks** (> 200 threshold) |
| 触发 stop | **stop_tick_moved_outside_planned_range_before_entry** (WARN, manual_intervention_required) |
| 含义 | frozen tick range [-200643, -200243] 不再适合当前链上状态 |
| **本轮必须做** | **re-read current_tick; re-compute tick range at runtime; abort if current tick outside new range; require fresh approval if drift > threshold** |
| 建议新 range 起点 | lower=-200900, upper=-200400 (3x margin); 实际由 v2 在 runtime 重新计算 |

## 3. 继承的关键事实

| 字段 | 值 |
|---|---|
| chain | base (chain_id 8453) |
| pool | `0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38` |
| pair | WETH/USDC |
| fee_tier | 100 (0.01%) |
| protocol | Uniswap V3 (Base) |
| npm | `0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1` |
| quoter_v2 | `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a` |
| weth | `0x4200000000000000000000000000000000000006` |
| usdc | `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| wallet | `0xb05b2872ace4564ff247555b6f7b097d31f3d835` |
| notional_first | 10 USD |
| hold_first | 15m |
| **frozen_tick_lower_legacy** | **-200643** (legacy; v2 不应直接使用) |
| **frozen_tick_upper_legacy** | **-200243** (legacy; v2 不应直接使用) |

## 4. 上游已读 artifacts

| 类别 | 路径 | 关键事实 |
|---|---|---|
| review FINAL_VERDICT | `reports/lp_base_10u_probe_execution_script_review/20260602_150957/FINAL_VERDICT.json` | status=PASS; execution_implementation_allowed_next=true |
| review ONEPAGE | `.../ONEPAGE_CN.md` | 概览 |
| review next impl spec (CN) | `.../NEXT_EXECUTION_IMPLEMENTATION_SPEC_CN.md` | 下一阶段 spec |
| review next impl spec (JSON) | `.../next_execution_implementation_spec.json` | 同上 (json) |
| build FINAL_VERDICT | `reports/lp_base_10u_probe_execution_script_build/20260602_135824/FINAL_VERDICT.json` | build stage verdict |
| v1 executor source | `scripts/lp_base_10u_probe_executor_v1.py` (845 lines, unchanged since 9811257) | build-stage skeleton |
| v1 build tests | `tests/test_lp_base_10u_probe_executor_v1_build.py` (40 tests) | build tests |
| v1 review tests | `tests/test_lp_base_10u_probe_executor_review_v1.py` (20 tests) | review tests |

## 5. 本轮范围

```text
implement_base_10u_probe_executor_v2_skeleton_with_guards_only_no_send
```

### 允许

- 创建 `scripts/lp_base_10u_probe_executor_v2.py`（新文件；v1 不变）
- 实现 `build_approve_exact_usdc_tx` / `build_revoke_usdc_tx`（结构化 tx 输出，不发送）
- 实现 `build_mint_position_tx`（deadline 实时生成）
- 实现 `build_decrease_liquidity_tx` / `build_collect_tx` / `build_revoke_allowance_tx`
- 实现 dynamic tick range recompute（重读 slot0）
- 实现 approval gate 含 `--i-understand-this-sends-real-transactions` 第二道 flag
- 实现 telemetry runtime writer（7 schema files）
- 实现 `execute-guarded` mode 永远返回 `EXECUTION_SEND_DISABLED_IN_IMPLEMENTATION_BUILD_STAGE`
- 运行 self-check（NO send triggered）
- 写安全审计证明 15 个 boolean safety flag 全部 false/disabled

### 禁止

- 执行 probe
- 发送 `eth_sendTransaction` / `eth_sendRawTransaction`
- 执行 approve / mint / increaseLiquidity / decreaseLiquidity / collect / burn / swap
- 启动 lpbot-live / lpbot-canary / lpbot-paper
- 自动 bridge / swap
- 自动加载私钥 / 助记词 / keystore
- 自动创建 signer / wallet client（无显式审批）
- 翻转 `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`
- 修改 build-stage v1 脚本或 tests
- 写 production lpbot 表
- 改任何策略执行路径

## 6. 通过

```text
all 8 upstream artifact categories read = yes
all upstream gates aligned = yes
previous status = PASS = yes
proceed_to_phase_C = true
```
