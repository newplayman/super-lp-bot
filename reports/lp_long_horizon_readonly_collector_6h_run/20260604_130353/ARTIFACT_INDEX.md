# LP Long Horizon Read-only Collector 6h Run Approval — Artifact Index

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物 (16 份)

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: workspace 安全检查 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: 8 input files + redirect 7D → STAGED 记录 |
| `input_evidence_audit.json` | Stage B: 字段化 |
| `MANUAL_APPROVAL_RECORDED_CN.md` | Stage C: approval 短语校验 + MANUAL_APPROVAL_RECORDED |
| `MANUAL_APPROVAL_RECORDED.json` | Stage C: approval 字段 (phrase hash, approved_next_stages=[], etc.) |
| `SIX_HOUR_RUN_CONFIG_CN.md` | Stage D: 6h run 参数冻结 (duration, checkpoint, abort) |
| `six_hour_run_config.json` | Stage D: 字段化 (含 adjusted_thresholds_6h) |
| `PRE_RUN_SAFETY_CHECK_CN.md` | Stage E: 启动前 7 项安全自检 |
| `pre_run_safety_check.json` | Stage E: 字段化 |
| `TMUX_START_HEALTHCHECK_CN.md` | Stage F: tmux 启动 + smoke check |
| `tmux_start_healthcheck.json` | Stage F: 字段化 |
| `launch_6h_tmux.sh` | tmux 启动脚本 (real-6h mode) |
| `launch_6h_short.sh` | tmux 启动脚本 (short mode) |
| `SIX_HOUR_RUN_SUMMARY_CN.md` | Stage H: 6h 跑汇总 |
| `six_hour_run_summary.json` | Stage H: 字段化 (含 dedup row counts) |
| `DATA_QUALITY_GATE_CN.md` | Stage H: data quality gate 评估 |
| `data_quality_gate.json` | Stage H: 13 项 gate 字段化 |
| `MARKET_REGIME_SUMMARY_CN.md` | Stage H: 7 regime × 7 timestamp |
| `market_regime_summary.json` | Stage H: 字段化 |
| `NEXT_STAGE_DECISION_CN.md` | Stage I: 下阶段决策 |
| `next_stage_decision.json` | Stage I: 字段化 |
| `FINAL_VERDICT.json` | Stage J: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage J: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage J: 本索引 (本文件) |
| `aggregate_summary.json` | Stage H: 6h aggregate 汇总 |

## research-only 输出 (data/ 目录, 不 commit)

```
data/lp_long_horizon/20260604_130353/
├── checkpoint_1_1311/    (real-mode 残留, killed)
│   ├── pool_snapshots.jsonl
│   ├── quote_snapshots.jsonl
│   ├── fee_velocity.jsonl
│   ├── liquidity_distribution.jsonl
│   ├── market_regime.jsonl
│   ├── actual_fee_accrual_placeholder.json
│   └── smoke_summary.json
├── checkpoint_1_131315/  (short mode 6 个新)
... (6 more, all with 7 files)
```

## 新增测试 (Stage K)

- `tests/test_lp_long_horizon_readonly_collector_6h_run_approval_v1.py` (本任务新增)

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/` (staged_request)
- `reports/lp_long_horizon_readonly_collector_fix_repeat/20260604_084008/` (fix_repeat)
- `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/` (smoke)
- `reports/lp_research_final_freeze/20260604_051254/` (final freeze)
- `scripts/lp_long_horizon_readonly_collector_v1.py` (collector 脚本, real 1-pass)
- `scripts/lp_long_horizon/` (8 lib modules)

未修改:
- 任何 `cmd/` `internal/` `migrations/` `configs/` `web/` 文件
- 任何 `data/dryrun*` `data/shadow*` `data/live*` 表
- 任何 `reports/lp_research_*` 已有文件 (read-only)
- 任何 collector 脚本代码

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `SIX_HOUR_RUN_SUMMARY_CN.md` (实际跑结果)
4. `DATA_QUALITY_GATE_CN.md` (gate 评估)
5. `NEXT_STAGE_DECISION_CN.md` (下阶段决策)
6. `MARKET_REGIME_SUMMARY_CN.md` (regime 分析)
7. `TMUX_START_HEALTHCHECK_CN.md` (tmux 启动 + smoke)
8. `MANUAL_APPROVAL_RECORDED_CN.md` (审批校验)
9. `reports/lp_long_horizon_readonly_collector_staged_request/20260604_123955/ONEPAGE_CN.md` (上游 staged_request)

## 后续阶段 (本任务不覆盖)

- `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` (本任务 recommended_next_stage, per WARN path)
  - 决定 fix 方案 (调低 runtime 阈值 / 调高 loop_count / 重跑真实 6h)
  - 写 6H_RUN_FIX_REPEAT_REQUEST_V1 报告
  - 重新走 6H_RUN_APPROVAL_V1 (manual approval)
  - 重新跑 6h, 写新一轮 FINAL_VERDICT
- `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (备选, 仅在 user 接受 6h WARN 时)
  - 重新提交 12h approval phrase
  - 重新 read-back 6h WARN
  - user 显式决定"接受 6h WARN, 进入 12h"
- 任何 `PAUSE_LP_LONG_HORIZON_READONLY_STAGE_RUN` (跨 stage WARN 累积时)
- 任何 `STOP_LP_RESEARCH_NOW` (safety 字段破坏时)
