# Artifact Index

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1`
- run_id: `20260602_135824`

| phase | artifact | 说明 |
|---|---|---|
| A | workspace safety check (git status) | HEAD=6f5566a; 仅 untracked runtime files; 无 dirty blocker |
| B | INPUT_EVIDENCE_AUDIT_CN.md, input_evidence_audit.json | 8 上游 spec review artifact categories 审计 |
| C | EXECUTOR_SCRIPT_DESIGN_CN.md, executor_script_design.json | executor 脚本设计 + 4 modes + hard-coded candidate |
| D | PREFLIGHT_COMMAND_SPEC_CN.md, preflight_command_spec.json | preflight-only command 规格 |
| E | UNSIGNED_PACKAGE_MODE_CN.md, unsigned_package_mode.json | print-unsigned mode 规格 |
| F | APPROVAL_PHRASE_PARSER_CN.md, approval_phrase_parser.json | validate-approval mode 规格 |
| G | TELEMETRY_WRITER_SKELETON_CN.md, telemetry_writer_skeleton.json | 5 telemetry schema files 规格 |
| H | STOP_CONDITION_ENGINE_CN.md, stop_condition_engine.json | 13 stops 评估 |
| I | EXECUTION_STUBS_DISABLED_CN.md, execution_stubs_disabled.json | 7 disabled stubs 规格 |
| J | EXECUTOR_SELF_CHECK_CN.md, executor_self_check.json | 11 个 case self-check 报告 |
| K | FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md | final verdict + 概览 + index |
| L | tests/test_lp_base_10u_probe_executor_v1_build.py | 22+ tests covering executor behaviors |
| (self-check artifacts) | reports/lp_base_10u_probe_execution_runtime/20260602_135824/ | preflight_result.json, unsigned_package.json, approval_validation.json |

## 关联 scripts/

| script | 用途 |
|---|---|
| **scripts/lp_base_10u_probe_executor_v1.py** | **本轮新增：executor skeleton（4 modes + 7 disabled stubs + 13 stop conditions + 5 telemetry schemas）** |

## 关联 tests/

| test | 用途 |
|---|---|
| **tests/test_lp_base_10u_probe_executor_v1_build.py** | **本轮新增：22+ tests** |

## 关联 upstream artifacts

| path | 用途 |
|---|---|
| reports/lp_base_probe_execution_spec_review/20260602_133221/FINAL_VERDICT.json | Phase B 上游 spec verdict |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_execution_candidate_freeze.json | Phase C 候选冻结 |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_execution_runbook.json | Phase C+D runbook |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_stop_conditions.json | Phase C+H stop conditions |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_actual_telemetry_spec.json | Phase C+G telemetry |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_execution_script_boundary.json | Phase C script boundary |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_execution_approval_template.json | Phase C+F approval phrase |
| reports/lp_base_probe_execution_spec_review/20260602_133221/base_probe_risk_acceptance.json | Phase C risk acceptance |
