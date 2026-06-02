# Artifact Index

- stage: `LP_BASE_10U_PROBE_EXECUTION_IMPLEMENTATION_V1`
- run_id: `20260602_163036`

| phase | artifact | 说明 |
|---|---|---|
| A | workspace safety check (git status) | HEAD=83b41b9; 仅 untracked runtime; 无 dirty blocker |
| B | INPUT_EVIDENCE_AUDIT_CN.md, input_evidence_audit.json | 8 上游 artifacts 审计; tick drift 累计 |
| C | EXECUTOR_SCRIPT_DESIGN_CN.md, executor_script_design.json | v2 executor skeleton 设计 (5 modes; 3 gates; 2 safety flags) |
| D | DYNAMIC_TICK_RANGE_RECOMPUTE_CN.md, dynamic_tick_range_recompute.json | 动态 tick range recompute; current_tick=-200708; drift=265; fresh_approval_required=true |
| E | APPROVE_EXACT_IMPLEMENTATION_CN.md, approve_exact_implementation.json | 3 个 approve builders; 5 tests pass; ApproveMax forbidden |
| F | MINT_TX_IMPLEMENTATION_CN.md, mint_tx_implementation.json | mint builder; deadline=now+3600; 修正 encode_mint 双 0x bug |
| G | EXIT_COLLECT_REVOKE_IMPLEMENTATION_CN.md, exit_collect_revoke_implementation.json | monitor/decrease/collect/revoke builders; 5 tests pass |
| H | TELEMETRY_RUNTIME_IMPLEMENTATION_CN.md, telemetry_runtime_implementation.json | 7 schema files 写到 local reports dir; 6 checks pass |
| I | EXECUTION_APPROVAL_GATE_IMPLEMENTATION_CN.md, execution_approval_gate_implementation.json | 3 hard gates + 2 safety defaults; 4 tests pass |
| J | IMPLEMENTATION_SELF_CHECK_CN.md, implementation_self_check.json | 5 self-check cases; execute-guarded aborts |
| K | IMPLEMENTATION_SECURITY_AUDIT_CN.md, implementation_security_audit.json | 15 boolean safety flags all PASS; 8 additional invariants pass |
| L | FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md | final verdict + 概览 + index |
| (self-check artifacts) | reports/lp_base_10u_probe_execution_runtime/20260602_163036/ | preflight.json, dynamic_tick_range.json, approval_check.json, unsigned_approve_package.json, unsigned_mint_package.json, stop_conditions.json, execution_gates.json |

## 关联 scripts/

| script | 用途 |
|---|---|
| **scripts/lp_base_10u_probe_executor_v2.py** | **本轮新增：executor v2 (961 lines)** — 5 modes; 3 hard gates; 2 safety flags; send hard-disabled |
| scripts/lp_base_10u_probe_executor_v1.py | (上游 build-stage skeleton, 845 lines, **unchanged**) |

## 关联 tests/

| test | 用途 |
|---|---|
| **tests/test_lp_base_10u_probe_execution_implementation_v1.py** | **本轮新增**（Phase M 中创建） |

## 关联 upstream artifacts

| path | 用途 |
|---|---|
| reports/lp_base_10u_probe_execution_script_review/20260602_150957/FINAL_VERDICT.json | 上游 review verdict |
| reports/lp_base_10u_probe_execution_script_review/20260602_150957/ONEPAGE_CN.md | 上游 ONEPAGE |
| reports/lp_base_10u_probe_execution_script_review/20260602_150957/NEXT_EXECUTION_IMPLEMENTATION_SPEC_CN.md | 上游 next impl spec |
| reports/lp_base_10u_probe_execution_script_review/20260602_150957/next_execution_implementation_spec.json | 上游 next impl spec (json) |
| reports/lp_base_10u_probe_execution_script_build/20260602_135824/FINAL_VERDICT.json | build stage verdict |
| scripts/lp_base_10u_probe_executor_v1.py | build stage 实际脚本 (unchanged) |
| tests/test_lp_base_10u_probe_executor_v1_build.py | build stage tests (40) |
| tests/test_lp_base_10u_probe_executor_review_v1.py | review stage tests (20) |
