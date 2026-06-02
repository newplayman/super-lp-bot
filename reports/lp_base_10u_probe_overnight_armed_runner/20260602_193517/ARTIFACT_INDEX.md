# Artifact Index — LP_BASE_10U_PROBE_OVERNIGHT_ARMED_RUNNER_BUILD_AND_READONLY_MONITOR_V1

- run_id: `20260602_193517`
- report dir: `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/`

## 本阶段产物

| phase | artifact | 路径 |
|---|---|---|
| C1 | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/INPUT_EVIDENCE_AUDIT_CN.md` |
| C1 | input_evidence_audit.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/input_evidence_audit.json` |
| C2 | ARMED_RUNNER_BUILD_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ARMED_RUNNER_BUILD_CN.md` |
| C2 | armed_runner_build.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/armed_runner_build.json` |
| C3 | ARMED_RUNNER_GATE_AUDIT_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ARMED_RUNNER_GATE_AUDIT_CN.md` |
| C3 | armed_runner_gate_audit.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/armed_runner_gate_audit.json` |
| C4 | ARMED_RUNNER_PREFLIGHT_SMOKE_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ARMED_RUNNER_PREFLIGHT_SMOKE_CN.md` |
| C4 | armed_runner_preflight_smoke.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/armed_runner_preflight_smoke.json` |
| C5/C6 | MONITOR_START_HEALTHCHECK_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/MONITOR_START_HEALTHCHECK_CN.md` |
| C5/C6 | monitor_start_healthcheck.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor_start_healthcheck.json` |
| C7 | MONITOR_FINALIZE_FLOW_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/MONITOR_FINALIZE_FLOW_CN.md` |
| C7 | MONITOR_FINALIZE_SCHEMA_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/MONITOR_FINALIZE_SCHEMA_CN.md` |
| C8 | FINAL_VERDICT.json | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/FINAL_VERDICT.json` |
| C8 | ONEPAGE_CN.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ONEPAGE_CN.md` |
| C8 | ARTIFACT_INDEX.md | `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/ARTIFACT_INDEX.md` |

## 本阶段新增 monitor 产物（tmux session 写）

- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/monitor.log`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/state.json`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/checkpoints/checkpoint_<ISO>.json` (持续追加)
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/readiness_timeseries.csv` (持续追加)
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/final_monitor_summary.json` (明早 finalize 后写)
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/FINAL_MONITOR_SUMMARY_CN.md` (明早 finalize 后写)

## 本阶段新增代码

- `scripts/lp_base_10u_probe_armed_runner_v1.py` (new; v2 不动)
- `scripts/lp_base_10u_probe_readiness_monitor_v1.py` (new)
- `tests/test_lp_base_10u_probe_armed_runner_monitor_v1.py` (new)

## 引用上游 artifacts

### Operator Execution Request V1 (20260602_190720, commit f578e4a)
- `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/FINAL_VERDICT.json`
- `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/OPERATOR_DECISION_MENU_CN.md`
- `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/operator_decision_menu.json`
- `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/FINAL_OPERATOR_APPROVAL_PHRASE_CN.md`
- `reports/lp_base_10u_probe_operator_execution_request/20260602_190720/final_operator_approval_phrase.json`

### Authorization Package V1 (20260602_184806, commit f89c02c)
### Final Execution Review V1 (20260602_182402, commit c18176f)
### Implementation V1 (20260602_163036, commit da6c012)

## 引用源码（未修改）

- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines) — line 974 raise `ExecutionSendDisabledInImplementationBuildStage`
