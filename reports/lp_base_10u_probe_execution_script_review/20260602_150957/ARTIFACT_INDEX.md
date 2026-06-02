# Artifact Index

- stage: `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_REVIEW_V1`
- run_id: `20260602_150957`
- note: re-verification of commit 596b411

| phase | artifact | 说明 |
|---|---|---|
| A | workspace safety check (git status) | HEAD=9811257; 仅 untracked runtime; 无 dirty blocker |
| B | INPUT_EVIDENCE_AUDIT_CN.md, input_evidence_audit.json | 14 上游 build artifacts 审计 |
| C | STATIC_SECURITY_REVIEW_CN.md, static_security_review.json | 11 项 static security checks; 0 dangerous matches |
| D | MODE_BEHAVIOR_REVIEW_CN.md, mode_behavior_review.json | 11 个 case all pass; **delta: preflight WARN** (tick drift 219) |
| E | PREFLIGHT_OUTPUT_REVIEW_CN.md, preflight_output_review.json | preflight_status=**WARN**; 1/13 stops; current_tick=-200662; 证明 stop engine 工作 |
| F | UNSIGNED_PACKAGE_REVIEW_CN.md, unsigned_package_review.json | all 5 flags true; candidate matches freeze; 修正上一轮关于 `mint_params.recipient` top-level 字段的措辞 |
| G | APPROVAL_PARSER_REVIEW_CN.md, approval_parser_review.json | 9 cases all pass; valid_phrase does not authorize execution |
| H | EXECUTION_STUBS_REVIEW_CN.md, execution_stubs_review.json | all 7 stubs raise ExecutionDisabledInBuildStage |
| I | TELEMETRY_SCHEMA_REVIEW_CN.md, telemetry_schema_review.json | 5 files designed; 3 written; local-only |
| J | NEXT_EXECUTION_IMPLEMENTATION_SPEC_CN.md, next_execution_implementation_spec.json | **新增 requirement**: future stage MUST re-read tick + re-approve range |
| K | FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md | final verdict + 概览 + index |
| (self-test artifacts) | reports/lp_base_10u_probe_execution_runtime/20260602_150957/ | preflight_result.json, unsigned_package.json, approval_validation.json |

## 关联 scripts/

| script | 用途 |
|---|---|
| **scripts/lp_base_10u_probe_executor_v1.py** | **本轮 review 对象：executor skeleton (845 lines, unchanged since 20260602_135824)** |

## 关联 tests/

| test | 用途 |
|---|---|
| **tests/test_lp_base_10u_probe_executor_review_v1.py** | **本轮新增：review-stage tests (20 tests)** |
| tests/test_lp_base_10u_probe_executor_v1_build.py | (上游 build stage tests, 40 tests) |

## 关联 upstream artifacts

| path | 用途 |
|---|---|
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/FINAL_VERDICT.json | 上游 build stage verdict |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/ONEPAGE_CN.md | 上游 ONEPAGE |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/EXECUTOR_SCRIPT_DESIGN_CN.md | 上游 executor design |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/executor_script_design.json | 上游 executor design (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/PREFLIGHT_COMMAND_SPEC_CN.md | 上游 preflight spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/preflight_command_spec.json | 上游 preflight spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/UNSIGNED_PACKAGE_MODE_CN.md | 上游 unsigned mode spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/unsigned_package_mode.json | 上游 unsigned mode spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/APPROVAL_PHRASE_PARSER_CN.md | 上游 approval parser spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/approval_phrase_parser.json | 上游 approval parser spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/STOP_CONDITION_ENGINE_CN.md | 上游 stop engine spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/stop_condition_engine.json | 上游 stop engine spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/EXECUTION_STUBS_DISABLED_CN.md | 上游 execution stubs spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/execution_stubs_disabled.json | 上游 execution stubs spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/TELEMETRY_WRITER_SKELETON_CN.md | 上游 telemetry writer spec |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/telemetry_writer_skeleton.json | 上游 telemetry writer spec (json) |
| scripts/lp_base_10u_probe_executor_v1.py | 上游 build stage 实际脚本 |
| tests/test_lp_base_10u_probe_executor_v1_build.py | 上游 build stage 实际 tests (40 tests) |
| reports/lp_base_10u_probe_execution_script_review/20260602_144843/FINAL_VERDICT.json | **上一轮 review（commit 596b411）**；本轮 re-verification 与之对比 |
