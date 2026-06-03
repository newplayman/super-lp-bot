# Artifact Index — LP_BASE_10U_PROBE_MONITOR_FINALIZE_AND_GO_NOGO_V1

- run_id: `20260603_040018`
- report_dir: `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/`

## 本阶段产物

| phase | artifact | 路径 |
|---|---|---|
| A | STAGE_A_WORKSPACE_SAFETY.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/STAGE_A_WORKSPACE_SAFETY.md` |
| B | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/INPUT_EVIDENCE_AUDIT_CN.md` |
| B | input_evidence_audit.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/input_evidence_audit.json` |
| C | MONITOR_PROCESS_STATUS_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/MONITOR_PROCESS_STATUS_CN.md` |
| C | monitor_process_status.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/monitor_process_status.json` |
| D | MONITOR_ARTIFACT_AUDIT_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/MONITOR_ARTIFACT_AUDIT_CN.md` |
| D | monitor_artifact_audit.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/monitor_artifact_audit.json` |
| E | MONITOR_FINALIZE_RESULT_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/MONITOR_FINALIZE_RESULT_CN.md` |
| E | monitor_finalize_result.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/monitor_finalize_result.json` |
| F | BASE_10U_PROBE_GO_NOGO_REVIEW_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/BASE_10U_PROBE_GO_NOGO_REVIEW_CN.md` |
| F | base_10u_probe_go_nogo_review.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/base_10u_probe_go_nogo_review.json` |
| G | NEXT_STAGE_DECISION_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/NEXT_STAGE_DECISION_CN.md` |
| G | next_stage_decision.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/next_stage_decision.json` |
| H | FINAL_VERDICT.json | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/FINAL_VERDICT.json` |
| H | ONEPAGE_CN.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/ONEPAGE_CN.md` |
| H | ARTIFACT_INDEX.md | `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/ARTIFACT_INDEX.md` |

## 本阶段新增测试

- `tests/test_lp_base_10u_probe_monitor_finalize_go_nogo_v1.py`（新文件）

## 引用上游 artifacts

### Overnight stage (20260602_193517, commit 4550b5f)
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/FINAL_VERDICT.json`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ONEPAGE_CN.md`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/MONITOR_START_HEALTHCHECK_CN.md`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/state.json`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/monitor.log`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/readiness_timeseries.csv`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/checkpoints/` (47 JSON)
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/final_monitor_summary.json`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/FINAL_MONITOR_SUMMARY_CN.md`

### 引用源码（未修改）
- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines; v2 line 974 raise 保留)
- `scripts/lp_base_10u_probe_armed_runner_v1.py` (armed runner v1; execute-armed 硬退出)
- `scripts/lp_base_10u_probe_readiness_monitor_v1.py` (monitor; --finalize 验证)
