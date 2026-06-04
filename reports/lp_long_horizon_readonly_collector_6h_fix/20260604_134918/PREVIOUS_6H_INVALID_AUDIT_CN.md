# Stage A — 上一轮 6h 无效审计 (Previous 6h Invalid Audit)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- run_id: `20260604_134918`
- branch: `feat/supabase-postgres-deployment`
- HEAD: `c36a179 research: finalize 6h long horizon readonly collector 20260604_130353`

## 0. 目的

审计上一轮 `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` (run_id
`20260604_130353`) 跑完成情况, 确认该跑**无效**, 不能作为 6h gate 真实数据.
本轮 `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
必须重跑真实 6h 墙钟, 严格 `actual_runtime_minutes >= 330`.

## 1. 审计目标

- [x] `previous_actual_runtime_minutes < 330`
- [x] `previous_short_mode_used = true`
- [x] `previous_gate_valid_for_12h = false`
- [x] `previous_should_not_advance_to_12h = true`

## 2. 上一轮关键数据 (per FINAL_VERDICT + six_hour_run_summary)

| 字段 | 实际值 | 应满足 | 状态 |
|---|---|---|---|
| `actual_runtime_minutes` | `2.75` | `>= 330` (real 6h 期望) | ❌ 不满足 |
| `actual_runtime_mode` | `short (LOOP_COUNT=6 SLEEP_SECONDS=10)` | `real_6h (LOOP_COUNT=6 SLEEP_SECONDS=3600)` | ❌ 不满足 |
| `gate_threshold_min_runtime_minutes` | `330` | n/a | (per task spec) |
| `runtime_meets_threshold` | `false` | `true` | ❌ |
| `data_quality_status` | `WARN_ACCEPTABLE` | `PASS` (per real 6h) | ❌ (因 runtime) |
| `gate_pass` | `false` | `true` | ❌ |
| `can_advance_to_12h` | `false` | `false` (WARN path) | ✅ (WARN 应停) |
| `recommended_next_stage` | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` | (本任务前身) | ✅ |
| `previous_short_mode_used` | `true` | `false` (应) | ❌ |

## 3. 上一轮无效原因分析

1. **真实 6h 模式启动后被 killed**:
   - tmux session `lp_long_horizon_6h_20260604_130353` 在 2026-06-04T13:11:12Z 启动
   - mode = real-6h (LOOP_COUNT=6 SLEEP_SECONDS=3600)
   - 实际 wallclock 仅跑 1.8 min, 在 13:13:00Z 被 killed
   - 原因: Agent 不能等 6h, 选择切换到短模式

2. **改用短模式 (LOOP_COUNT=6 SLEEP_SECONDS=10)**:
   - 6 个 checkpoint 全部跑出 (5+30+25+5+7+1+1 records / checkpoint)
   - 实际 wallclock 2.75 min, 短模式等价于 6h pipeline 的 6-iteration 验证
   - **但** 短模式**不满足** `actual_runtime_minutes >= 330` 的 6h gate 阈值

3. **结果**: data_quality_status = WARN_ACCEPTABLE, gate_pass = false,
   can_advance_to_12h = false, 6h 收口但不晋级.

## 4. 上一轮 6h 数据保留 vs 丢弃

**保留**: data/lp_long_horizon/20260604_130353/ 7 个 checkpoint 仍存在
(短模式产生, real_data, no fabrication, 真实 classifier 输出).
**不**作 6h gate 数据, 但可作 R1 阶段 baseline 校对.

**丢弃**: 不作 6h gate 决策依据. 真实 6h gate 必须本任务重跑 (real wallclock).

## 5. 上一轮 safety 字段 (locked, 全部 PASS)

- `wallet_or_tx_touched = false`
- `transaction_sent = false`
- `send_hard_disable_still_active = true`
- `no_paid_rpc_integration = true`
- `no_protocol_re_run = true`
- `no_long_running_daemon = true`
- `no_signer_creation = true`
- `no_12h_24h_48h_72h_7d_run = true`
- `no_auto_advance = true`

**结论**: 上一轮 safety 全部 locked, **不**因此次 WARN 而破防.

## 6. 上一轮 best practices (本任务可复用)

- ✅ Approval 短语校验: exact match, sha256 锁定
- ✅ MANUAL_APPROVAL_RECORDED.json schema 完整 (approved_next_stages=[])
- ✅ tmux session 命名约定 (lp_long_horizon_6h_${RUN_ID})
- ✅ 7 类 abort condition 完整
- ✅ 6 类 data 维度 + JSONL fallback
- ✅ 5 unique pool_address 来源 (final_freeze 5 protocol verdict)

## 7. 上一轮与本任务的关键差异

| 维度 | 上一轮 (130353) | 本任务 (134918) |
|---|---|---|
| 阶段名 | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1` |
| mode | short (10s sleep, 2.75 min) | real_6h (3600s sleep, ≥330 min) |
| 启动后行为 | Agent 自己跑完 | tmux + supervisor 独立跑, Agent 等早回报 |
| 收口方式 | Agent 自己 finalize | supervisor 自动 finalize + 自动 commit/push |
| 期望 gate | WARN_ACCEPTABLE (因 short mode) | PASS (real wallclock) |

## 8. 重要: 严禁用短模式冒充 6h (本任务硬性要求)

任务规范明确:
> "禁止使用 LOOP_COUNT=6 SLEEP_SECONDS=10 这类短模式冒充"
> "禁止 kill 真实 6h 后用短模式替代"

本任务的 supervisor 脚本**必须**:
- `SLEEP_SECONDS=3600` (per checkpoint, real 6h)
- `LOOP_COUNT=6` (6 hour, no override)
- **不允许** `SLEEP_SECONDS=10` 或 `SLEEP_SECONDS<300` (短模式 hard reject)
- **不允许** Agent kill 真实 6h 后用短模式替代
- **不允许** `loop_sleep_override_allowed=true`

如 supervisor 检测到 short mode 或 override, **立即 abort** + 写 FINAL_VERDICT
status=FAIL.

## 9. 上一轮 `previous_should_not_advance_to_12h = true` 确认

| 维度 | 上一轮状态 | 12h 可启? |
|---|---|---|
| runtime 不达标 (2.75 < 330) | ❌ | ❌ NO |
| gate_pass | false | ❌ NO |
| can_advance_to_12h | false | ❌ NO |
| 12h manual approval | 未记录 | ❌ NO (严禁隐式) |
| auto_advance_allowed | false (locked) | ❌ NO |

✅ `previous_should_not_advance_to_12h = true` 确认.

## 10. 结论

上一轮 6h (130353) **无效** (`actual_runtime_minutes=2.75 < 330`, `short_mode_used=true`,
`gate_pass=false`). 本任务 `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
必须**重跑真实 6h 墙钟**, 严格 `actual_runtime_minutes >= 330` 才能 gate PASS.
不允许用短模式冒充. 不允许 kill 真实 6h 后用短模式替代. supervisor 脚本必须 hard-reject
short mode override.

Stage A 通过. 进入 Stage B (workspace).
