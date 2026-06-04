# LP Long Horizon Read-only Collector Staged Run Request — Artifact Index

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: workspace 安全检查 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: 8 input files + redirect 7D → STAGED 记录 |
| `input_evidence_audit.json` | Stage B: 字段化 |
| `STAGED_RUN_PLAN_CN.md` | Stage C: 6 阶段 + first=6h + auto_advance=false |
| `staged_run_plan.json` | Stage C: 字段化 |
| `STAGE_GATE_RULES_CN.md` | Stage D: 13 core gate + per-stage thresholds |
| `stage_gate_rules.json` | Stage D: 字段化 |
| `STAGE_APPROVAL_TEMPLATES_CN.md` | Stage E: 6 APPROVE + reject + pause phrase |
| `stage_approval_templates.json` | Stage E: 字段化 |
| `STAGE_RUNTIME_BUDGET_CN.md` | Stage F: size + RPC + CPU + RAM 估算 |
| `stage_runtime_budget.json` | Stage F: 字段化 |
| `STAGE_FAILURE_AND_ABORT_POLICY_CN.md` | Stage G: 5 abort conditions + 3 decision paths |
| `stage_failure_and_abort_policy.json` | Stage G: 字段化 |
| `STAGED_TMUX_SCRIPT_TEMPLATE_CN.md` | Stage H: tmux 启动模板 (disabled by default) |
| `staged_tmux_script_template.json` | Stage H: 字段化 |
| `FINAL_VERDICT.json` | Stage I: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage I: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage I: 本索引 (本文件) |

## 新增测试 (Stage J)

- `tests/test_lp_long_horizon_readonly_collector_staged_request_v1.py` (本任务新增)

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/` (12 份 fix_repeat 产物)
- `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/` (12 份 smoke 产物)
- `reports/lp_research_final_freeze/20260604_051254/` (final freeze)
- `scripts/lp_long_horizon/` (8 个 lib 模块, fix_repeat 已 commit)
- `scripts/lp_long_horizon_readonly_real_data_smoke_v1.py` (fix_repeat runner)
- `tests/test_lp_long_horizon_readonly_collector_fix_repeat_v1.py` (fix_repeat pytest)

未修改:
- `docs/LPBOT_RESEARCH_STATUS_CN.md` (本阶段是 planning, 不是口径修正)
- `README.md`
- 任何 `cmd/` `internal/` `migrations/` `configs/` `web/` 文件
- 任何 `data/dryrun*` `data/shadow*` `data/live*` 表
- 任何 `reports/lp_research_*` 已有文件 (read-only)
- 任何 collector 脚本代码

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `STAGED_RUN_PLAN_CN.md` (6 阶段计划)
4. `STAGE_GATE_RULES_CN.md` (13 core gate)
5. `STAGE_APPROVAL_TEMPLATES_CN.md` (审批短语)
6. `STAGE_RUNTIME_BUDGET_CN.md` (运行时预算)
7. `STAGE_FAILURE_AND_ABORT_POLICY_CN.md` (失败 / abort 策略)
8. `STAGED_TMUX_SCRIPT_TEMPLATE_CN.md` (tmux 模板)
9. `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/ONEPAGE_CN.md` (上游 fix_repeat)

## 后续阶段 (本任务不覆盖)

- `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` (本任务 recommended_next_stage)
  - 接收 6h APPROVAL_RECORD.json
  - 实装 paid_rpc_indexer
  - uncomment tmux 启动模板
  - 跑 6h stage
  - 写 6h FINAL_VERDICT.json
- `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (12h 跑, manual approval 后)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_24H_RUN_APPROVAL_V1` (24h 跑, manual approval 后)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_48H_RUN_APPROVAL_V1` (48h 跑, manual approval 后)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_72H_RUN_APPROVAL_V1` (72h 跑, manual approval 后)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_APPROVAL_V1` (7d 跑, manual approval 后, 仅在 5 个前置 stage 全部 PASS 后才考虑)
- 任何 `STAGE_RUN_FIX_REPEAT_REQUEST_V1` (失败时)
- 任何 `PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN` (跨多 stage FAIL 时)
- 任何 `STOP_LP_RESEARCH_NOW` (safety 字段破坏时)
