# Artifact Index

- stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`
- run_id: `20260602_112400`

| phase | artifact | 说明 |
|---|---|---|
| A | workspace `/tmp/_base_dry_run_id`, `/tmp/_base_dry_report_dir` | RUN_ID + REPORT_DIR persisted |
| B | INPUT_EVIDENCE_AUDIT_CN.md, input_evidence_audit.json | 14 上游 artifact 审计 + 本轮范围/禁区 |
| C | BASE_CANDIDATE_FREEZE_CN.md, base_candidate_freeze.json | 候选池冻结 (WETH/USDC 0x72ab388e) |
| D | BASE_RPC_CONTRACT_READINESS_CN.md, base_rpc_contract_readiness.json | Base RPC + 6 合约 getCode 校验 |
| E | BASE_WALLET_BALANCE_ALLOWANCE_REFRESH_CN.md, base_wallet_balance_allowance_refresh.json | 余额 + allowance 刷新 (block 46807131) |
| F | BASE_POOL_STATE_REFRESH_CN.md, base_pool_state_refresh.json | 池 slot0 / liquidity 刷新 (block 46807634) |
| G | TICK_RANGE_PROPOSAL_CN.md, tick_range_proposal.json | 3 档 tick range；推荐 medium |
| H | TOKEN_AMOUNT_CALC_CN.md, token_amount_calc.json | 10U/20U token amount (in-range math) |
| I | WALLET_BOUND_UNSIGNED_PACKAGE_CN.md, wallet_bound_unsigned_package.json | wallet-bound unsigned tx package |
| J | GAS_ESTIMATE_FEASIBILITY_CN.md, gas_estimate_feasibility.json | gas estimate (live approve + inherited mint) |
| K | BASE_PROBE_MANUAL_APPROVAL_CHECKPOINT_CN.md | 人工审批 checkpoint + 正则 |
| L | FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md | final verdict + 概览 + index |

## 关联 scripts/

| script | 用途 |
|---|---|
| scripts/lp_base_rpc_and_contract_readiness_v1_readonly.py | Phase D |
| scripts/lp_base_wallet_balance_allowance_refresh_v1_readonly.py | Phase E |
| scripts/lp_base_pool_state_refresh_v1_readonly.py | Phase F |
| scripts/lp_base_unsigned_tx_package_builder_v1_readonly.py | Phase I |
| scripts/lp_base_gas_estimate_feasibility_v1_readonly.py | Phase J |

## 关联 upstream artifacts

| path | 用途 |
|---|---|
| reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json | Phase B 上游 stage verdict |
| reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/base_candidate_from_existing_artifacts.json | Phase B+C 候选池发现 |
| reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/evm_wallet_crosschain_balance_audit.json | Phase B+E 余额基线 |
| reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/evm_wallet_crosschain_allowance_audit.json | Phase B+E allowance 基线 |
| reports/lp_precise_quote/20260601_120001/precise_quote_results.csv | Phase F QuoterV2 继承 |
| reports/lp_v3_tick_liquidity_fix/20260601_132644/v3_tick_liquidity_v2_results.csv | Phase B+F tick 基线 |
| reports/lp_real_cost_model/20260601_141103/real_cost_model_results.csv | Phase J mint gas 继承 |
| reports/lp_real_fee_accrual/20260601_143401/real_fee_economics_preview.csv | Phase B EV proxy 基线 |
