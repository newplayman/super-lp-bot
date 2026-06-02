# Artifact Index — LP_BASE_10U_PROBE_FINAL_EXECUTION_REVIEW_V1

- run_id: `20260602_182402`
- report dir: `reports/lp_base_10u_probe_final_execution_review/20260602_182402/`
- runtime telemetry dir: `reports/lp_base_10u_probe_execution_runtime/20260602_182402/`

## 报告 artifacts

| phase | artifact | 路径 |
|---|---|---|
| B | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/INPUT_EVIDENCE_AUDIT_CN.md` |
| B | input_evidence_audit.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/input_evidence_audit.json` |
| C | EXECUTOR_V2_STATIC_SECURITY_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/EXECUTOR_V2_STATIC_SECURITY_REVIEW_CN.md` |
| C | executor_v2_static_security_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/executor_v2_static_security_review.json` |
| D | DYNAMIC_TICK_RANGE_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/DYNAMIC_TICK_RANGE_FINAL_REVIEW_CN.md` |
| D | dynamic_tick_range_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/dynamic_tick_range_final_review.json` |
| E | APPROVAL_GATE_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/APPROVAL_GATE_FINAL_REVIEW_CN.md` |
| E | approval_gate_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/approval_gate_final_review.json` |
| F | APPROVE_EXACT_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/APPROVE_EXACT_FINAL_REVIEW_CN.md` |
| F | approve_exact_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/approve_exact_final_review.json` |
| G | MINT_EXIT_COLLECT_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/MINT_EXIT_COLLECT_FINAL_REVIEW_CN.md` |
| G | mint_exit_collect_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/mint_exit_collect_final_review.json` |
| H | RUNTIME_SELF_CHECK_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/RUNTIME_SELF_CHECK_FINAL_REVIEW_CN.md` |
| H | runtime_self_check_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/runtime_self_check_final_review.json` |
| I | TELEMETRY_AND_ARTIFACT_FINAL_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/TELEMETRY_AND_ARTIFACT_FINAL_REVIEW_CN.md` |
| I | telemetry_and_artifact_final_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/telemetry_and_artifact_final_review.json` |
| J | FINAL_EXECUTION_GATE_REVIEW_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/FINAL_EXECUTION_GATE_REVIEW_CN.md` |
| J | final_execution_gate_review.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/final_execution_gate_review.json` |
| K | FINAL_VERDICT.json | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/FINAL_VERDICT.json` |
| K | ONEPAGE_CN.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/ONEPAGE_CN.md` |
| K | ARTIFACT_INDEX.md | `reports/lp_base_10u_probe_final_execution_review/20260602_182402/ARTIFACT_INDEX.md` |

## runtime telemetry artifacts（脚本写入；本 review 调用 4 个 mode 产生）

| schema | path |
|---|---|
| preflight | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/preflight.json` |
| dynamic_tick_range | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/dynamic_tick_range.json` |
| approval_check | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/approval_check.json` |
| unsigned_approve_package | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/unsigned_approve_package.json` |
| unsigned_mint_package | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/unsigned_mint_package.json` |
| stop_conditions | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/stop_conditions.json` |
| execution_gates | `reports/lp_base_10u_probe_execution_runtime/20260602_182402/execution_gates.json` |

## 引用上游 artifacts（implementation 20260602_163036）

- `reports/lp_base_10u_probe_execution_implementation/20260602_163036/FINAL_VERDICT.json`
- `reports/lp_base_10u_probe_execution_implementation/20260602_163036/ONEPAGE_CN.md`
- 其他 implementation phase artifacts（see Stage B INPUT_EVIDENCE_AUDIT_CN.md）

## 引用源码

- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines) — 审查目标
- `scripts/lp_base_10u_probe_executor_v1.py` (845 lines) — build-stage skeleton（保持不变）
- `tests/test_lp_base_10u_probe_execution_implementation_v1.py` (359 lines)
- `tests/test_lp_base_10u_probe_final_execution_review_v1.py` — 本 review 新增（见 Stage L）
