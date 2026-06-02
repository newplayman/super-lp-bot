# Artifact Index

- stage: `LP_BASE_10_20U_PROBE_EXECUTION_SPEC_REVIEW_V1`
- run_id: `20260602_133221`

| phase | artifact | 说明 |
|---|---|---|
| A | workspace safety check (git status) | HEAD=a4422d1; 仅 untracked runtime files; 无 dirty blocker |
| B | INPUT_EVIDENCE_AUDIT_CN.md, input_evidence_audit.json | 16 上游 artifact 审计 + 本轮范围/禁区 |
| C | BASE_PROBE_EXECUTION_CANDIDATE_FREEZE_CN.md, base_probe_execution_candidate_freeze.json | 候选冻结（10U first, 15m hold） |
| D | BASE_PROBE_EXECUTION_RUNBOOK_CN.md, base_probe_execution_runbook.json | Step 0-5 设计（未执行） |
| E | BASE_PROBE_STOP_CONDITIONS_CN.md, base_probe_stop_conditions.json | 20 个 hard stop + handling actions |
| F | BASE_PROBE_ACTUAL_TELEMETRY_SPEC_CN.md, base_probe_actual_telemetry_spec.json | 6 telemetry schemas (no production writes) |
| G | BASE_PROBE_EXECUTION_SCRIPT_BOUNDARY_CN.md, base_probe_execution_script_boundary.json | 7 允许 + 11 禁止 + 未来审批短语模板 |
| H | BASE_PROBE_EXECUTION_APPROVAL_TEMPLATE_CN.md, base_probe_execution_approval_template.json | 人工审批模板（template only, non-effective this round） |
| I | BASE_PROBE_RISK_ACCEPTANCE_CN.md, base_probe_risk_acceptance.json | 风险声明（EV 负，不是盈利策略） |
| J | FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md | final verdict + 概览 + index |

## 关联 upstream artifacts

| path | 用途 |
|---|---|
| reports/lp_base_probe_dry_run_builder/20260602_112400/FINAL_VERDICT.json | Phase B 上游 stage verdict |
| reports/lp_base_probe_dry_run_builder/20260602_112400/ONEPAGE_CN.md | Phase B 概览 |
| reports/lp_base_probe_dry_run_builder/20260602_112400/base_candidate_freeze.json | Phase C 池冻结 |
| reports/lp_base_probe_dry_run_builder/20260602_112400/base_wallet_balance_allowance_refresh.json | Phase C 余额 |
| reports/lp_base_probe_dry_run_builder/20260602_112400/base_pool_state_refresh.json | Phase C slot0 |
| reports/lp_base_probe_dry_run_builder/20260602_112400/tick_range_proposal.json | Phase C + D tick range |
| reports/lp_base_probe_dry_run_builder/20260602_112400/token_amount_calc.json | Phase C + D amount |
| reports/lp_base_probe_dry_run_builder/20260602_112400/wallet_bound_unsigned_package.json | Phase D mint data |
| reports/lp_base_probe_dry_run_builder/20260602_112400/gas_estimate_feasibility.json | Phase D + J gas |
| reports/lp_base_probe_dry_run_builder/20260602_112400/BASE_PROBE_MANUAL_APPROVAL_CHECKPOINT_CN.md | 上游 dry-run approval checkpoint (regex 不同) |
| reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json | 二级上游 (router) |
| reports/lp_real_cost_model/20260601_141103/real_cost_model_results.csv | upstream EV proxy |
| reports/lp_real_fee_accrual/20260601_143401/real_fee_economics_preview.csv | upstream actual_position_fee_lineage_missing |
| reports/lp_precise_quote/20260601_120001/precise_quote_results.csv | upstream quote |
| reports/lp_v3_tick_liquidity_fix/20260601_132644/v3_tick_liquidity_v2_results.csv | upstream tick + liquidity |

## 关联 scripts（本轮**未**新增）

| script | 用途 |
|---|---|
| scripts/lp_base_rpc_and_contract_readiness_v1_readonly.py | (上游 dry-run Phase D) |
| scripts/lp_base_wallet_balance_allowance_refresh_v1_readonly.py | (上游 dry-run Phase E) |
| scripts/lp_base_pool_state_refresh_v1_readonly.py | (上游 dry-run Phase F) |
| scripts/lp_base_unsigned_tx_package_builder_v1_readonly.py | (上游 dry-run Phase I) |
| scripts/lp_base_gas_estimate_feasibility_v1_readonly.py | (上游 dry-run Phase J) |

**本轮（execution spec review）不新增任何 scripts/**。所有 spec 都在 reports/ 目录下的 markdown + json 描述，未来 `LP_BASE_10U_PROBE_EXECUTION_SCRIPT_BUILD_V1` 才会基于这些 spec 构建 executor 脚本。
