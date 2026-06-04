# Stage G — Stage Failure & Abort Policy (阶段失败 / 中止策略)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`

## 0. 目的

定义 6 阶段 (6h/12h/24h/48h/72h/7d) 各自的失败 / 中止策略. 当某阶段
FAIL 时, 走哪条路径 (fix_repeat / pause / stop) 由本策略决定.

## 1. abort condition (来自 fix_repeat_v1 5 类)

每阶段跑期间, runner 检查 5 类 abort condition (per `lp_long_horizon.utils.abort`):

| # | abort condition | 触发后行为 |
|---|---|---|
| 1 | `consecutive_429` (5 连发) | runner 立即 abort, 写当前 snapshot, 退出 |
| 2 | `error_rate` (>= 20%) | runner abort |
| 3 | `write_failure` (jsonl/sqlite 写盘失败) | runner abort |
| 4 | `safety_self_check_failure` (banned token runtime 检出) | runner abort, 写 GIT_PUBLISH_BLOCKED_CN.md |
| 5 | `banned_token_detected` (与 #4 类似) | runner abort |

## 2. abort 后必做

runner abort 后**必须**做 (per STAGE_ABORT_TEMPLATE):

1. close store (sqlite + jsonl)
2. 写 `smoke_summary.json` 包含 `aborted=true, abort_reason, abort_at`
3. 写 `STAGE_ABORT.json` 含 abort_kind + abort_reason + abort_at + last_completed_step
4. 写 `FINAL_VERDICT.json` 含 `data_quality_status=FAIL, abort_kind, abort_reason`
5. 写 failure subreport:
   `reports/lp_long_horizon_readonly_collector_<STAGE>_run_failure_<RUN_ID>/`
   - `STAGE_FAILURE_REPORT_CN.md` (root cause + fix suggestion)
   - `failure_summary.json`
6. exit non-zero (1-7 视 abort_kind)

## 3. fix_repeat vs pause vs stop 决策

### 3.1 fix_repeat (推荐, 大多数情况)

**触发**:
- 5 类 abort condition 任一触发, 但 root cause 已明确
- 13 项 gate 1-3 项 FAIL, 但其他 stage 仍能跑
- 单次 retry 可解决 (e.g. 加 paid RPC, 改采样频率)

**行为**:
- 写 `LP_LONG_HORIZON_READONLY_COLLECTOR_<STAGE>_RUN_FIX_REPEAT_REQUEST` 报告
- 列 5-10 个具体修复动作
- 重新进入 STAGE_RUN_APPROVAL_V1 阶段 (manual approval 重新走)
- 不自动 retry

### 3.2 pause (跨多 stage 数据质量退化)

**触发**:
- 连续 3 个 stage 都 FAIL (data_quality_status=FAIL)
- 同一 abort_kind 连续 2 个 stage 触发
- 外部市场冲击 (e.g. 大盘崩盘, 数据失去代表性)
- 手动 audit 需求

**行为**:
- 写 `PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=<...>` 短语记录
- 停止所有 stage advance
- 等 manual unpause 决策
- unpause 后, 走 `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_REQUEST_FIX_REPEAT`
  重新设计 staged plan

### 3.3 stop (LP research 整体停止)

**触发**:
- safety 字段破坏 (e.g. real production write, real wallet/tx 触发)
- ban / 法律 / 合规问题
- 5 个 stage 都 pause, 仍无法恢复
- `STOP_LP_RESEARCH_NOW` 决议

**行为**:
- 写 `STOP_LP_RESEARCH_NOW` 报告
- 关闭所有 LP research 文件入口
- 不再 advance 任何 stage
- 后续路径: 归档 / 公开学习材料 / 项目方向 A/B/C/D (per final freeze NEXT_PROJECT_DIRECTION)

## 4. 决策树

```
[stage FAIL]
   │
   ├─ root cause 已明确 + 单次可修? ──── YES ─→ fix_repeat
   │                                    ──── NO
   │                                       │
   │                                       ├─ 连续 3 stage FAIL? ──── YES ─→ pause
   │                                       │                       ──── NO
   │                                       │                          │
   │                                       │                          └─ safety 字段破坏? ──── YES ─→ stop
   │                                       │                                                 ──── NO
   │                                       │                                                    │
   │                                       └─ [回到 fix_repeat, 加强 audit] ────────────────────┘
```

## 5. fix_repeat 后的 stage 重启流程

fix_repeat 不直接重跑 stage, 必须走完:

1. 写 `LP_LONG_HORIZON_READONLY_COLLECTOR_<STAGE>_RUN_FIX_REPEAT_REQUEST_V1`
2. 修复动作实施 (e.g. 实装 paid RPC, 调小采样频率)
3. 写 regression smoke (per fix_repeat_v1 经验)
4. 重新申请 STAGE_RUN_APPROVAL_V1 (manual approval)
5. 重新跑 stage

## 6. pause 后的 unpause 流程

pause 后, 不直接 unpause. 必须:

1. 写 `UNPAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN reason=<...>` 短语
2. audit 报告 (root cause 分析)
3. 重新设计 staged plan (e.g. 改 stage 长度, 加 pool, 换 data source)
4. 走 `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_REQUEST_FIX_REPEAT`
5. 重新申请 first stage (6h) approval

## 7. 失败复盘 (per stage)

每阶段失败时, runner 写 `STAGE_FAILURE_REPORT_CN.md`:

```markdown
# <STAGE> Failure Report

## abort_kind
<consecutive_429 | error_rate | write_failure | safety_self_check_failure | banned_token_detected>

## abort_reason
<具体描述>

## last_completed_step
<最后一次成功的 step, e.g. "pool_snapshot 60/60 完成, quote_snapshot 1230/2160">

## root_cause
<根因分析, 1-3 段>

## impact_assessment
<影响: 哪些 record 已写, 哪些丢失, 哪些 partial>

## fix_repeat_recommendation
<具体修复动作, 5-10 项>

## next_action_decision
<fix_repeat / pause / stop, 含理由>

## cross_stage_impact
<是否影响其他 stage, 怎么影响>

## audit_trail
<abort 时间戳, abort_kind, abort_reason, last_completed_step, 记录人>
```

## 8. 失败不掩盖 (no concealment)

任何 abort 必须在 FINAL_VERDICT.json 明确写出:

```json
{
  "data_quality_status": "FAIL",
  "abort_kind": "consecutive_429",
  "abort_reason": "5 consecutive 429 from solana_rpc_public",
  "abort_at": "ISO 8601 UTC",
  "last_completed_step": "pool_snapshot 5/5, quote_snapshot 120/2160",
  "next_action": "fix_repeat",
  "no_concealment": true
}
```

audit 不可篡改 (per STAGE_FAILURE_NO_TAMPER 原则).

## 9. 跨 stage 失败传染防护

如果 stage 1 (6h) FAIL, 不能让 stage 2/3/4/5/6 跑 (即使已 approval).
具体:
- `auto_advance_allowed = false` 保证 stage 不会自动跑
- 失败 stage 的 FINAL_VERDICT.json `data_quality_status=FAIL` 标记
- 任何 advance attempt 检测到前一阶段 FAIL → abort

## 10. 结论

失败 / 中止策略完整: 5 类 abort condition + 3 种决策路径 (fix_repeat /
pause / stop) + 决策树 + 复盘模板 + 跨 stage 防护. Stage G 通过.
进入 Stage H (tmux 模板).
