# LP Long Horizon Read-only Collector Smoke — Artifact Index

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: workspace 安全检查 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: 8 input files read-back + 10 locked + 13 prohibitions |
| `input_evidence_audit.json` | Stage B: 字段化 |
| `COLLECTOR_CLI_REVIEW_CN.md` | Stage C: 7 flags + 12 hard-rejected modes + 5 task spec deviations |
| `collector_cli_review.json` | Stage C: 字段化 |
| `COLLECTOR_DESIGN_MODE_RESULT_CN.md` | Stage D: design mode 跑通, exit 0, 0 files written as expected |
| `collector_design_mode_result.json` | Stage D: 字段化 |
| `COLLECTOR_SMOKE_RESULT_CN.md` | Stage E: smoke 30 quote + 5 pool + 25 fee + 5 liq + 7 regime + 1 placeholder + 1 summary |
| `collector_smoke_result.json` | Stage E: 字段化 |
| `SMOKE_OUTPUT_SCHEMA_VALIDATION_CN.md` | Stage F: 6/6 schema pass; 0 secret; 0 production; 0 shadow |
| `smoke_output_schema_validation.json` | Stage F: 字段化 |
| `MARKET_REGIME_SMOKE_VALIDATION_CN.md` | Stage G: 7/7 regimes placeholder, smoke_placeholder=true, no fabrication |
| `market_regime_smoke_validation.json` | Stage G: 字段化 |
| `COLLECTOR_HEALTH_AND_FAILURE_MODE_CN.md` | Stage H: smoke OK + long-run failure mode spec + readiness 0/9 |
| `collector_health_and_failure_mode.json` | Stage H: 字段化 |
| `LONG_HORIZON_COLLECTOR_NEXT_STAGE_DECISION_CN.md` | Stage I: FIX_REPEAT chosen, 7 fix tasks identified |
| `long_horizon_collector_next_stage_decision.json` | Stage I: 字段化 |
| `FINAL_VERDICT.json` | Stage J: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage J: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage J: 本索引 (本文件) |

## smoke 实际输出 (research-only, 不在 commit 范围)

`data/lp_long_horizon/20260604_081432/collector_smoke/`:
- `pool_snapshots.jsonl` 5 records / 2490B
- `quote_snapshots.jsonl` 30 records / 8778B
- `fee_velocity.jsonl` 25 records / 7900B
- `liquidity_distribution.jsonl` 5 records / 1383B
- `market_regime.jsonl` 7 records / 1516B
- `actual_fee_accrual_placeholder.json` 1 object / 729B
- `smoke_summary.json` 1 object / 1461B

(这些文件不会被 commit, 已在 .gitignore pattern 之外但 git status 仍可见;
最终 commit 只含 REPORT_DIR + tests + scripts, 不含 data/ 目录)

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/` (12 份 pipeline 产物)
- `scripts/lp_long_horizon_readonly_collector_v1.py` (collector 脚本)

## 新增测试

- `tests/test_lp_long_horizon_readonly_collector_smoke_v1.py` (本任务新增)

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `COLLECTOR_SMOKE_RESULT_CN.md` (smoke 实际执行结果)
4. `SMOKE_OUTPUT_SCHEMA_VALIDATION_CN.md` (6/6 schema pass)
5. `LONG_HORIZON_COLLECTOR_NEXT_STAGE_DECISION_CN.md` (FIX_REPEAT 决策依据)
6. `reports/lp_long_horizon_readonly_data_pipeline/20260604_062324/ONEPAGE_CN.md` (上游 pipeline 一页纸)

## 后续阶段 (本任务不覆盖)

- `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT` (本任务 recommended_next_stage)
  - 实装 4 source adapter
  - 实装 7 regime classifier
  - 接入 paid RPC / indexer
  - 实装 5 abort condition
  - manual approval 流程
  - 回归 smoke
- `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` (FIX_REPEAT 完成后)
- `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_V1` (manual approval 完成后)
- ... 后续 R0 / R1 / R2 / R3 / R4 / R5 阶段
