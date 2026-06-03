# Artifact Index — LP_SOLANA_LP_CONNECTOR_DESIGN_V1

- run_id: `20260603_080347`
- report_dir: `reports/lp_solana_connector_design/20260603_080347/`

## 本阶段产物

| phase | artifact | 路径 |
|---|---|---|
| A | STAGE_A_WORKSPACE_SAFETY.md | `reports/lp_solana_connector_design/20260603_080347/STAGE_A_WORKSPACE_SAFETY.md` |
| B | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_solana_connector_design/20260603_080347/INPUT_EVIDENCE_AUDIT_CN.md` |
| B | input_evidence_audit.json | `reports/lp_solana_connector_design/20260603_080347/input_evidence_audit.json` |
| C | SOLANA_LP_PROTOCOL_TARGET_MATRIX_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_LP_PROTOCOL_TARGET_MATRIX_CN.md` |
| C | solana_lp_protocol_target_matrix.json | `reports/lp_solana_connector_design/20260603_080347/solana_lp_protocol_target_matrix.json` |
| C | solana_lp_protocol_target_matrix.csv | `reports/lp_solana_connector_design/20260603_080347/solana_lp_protocol_target_matrix.csv` |
| D | SOLANA_DATA_SOURCE_FEASIBILITY_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_DATA_SOURCE_FEASIBILITY_CN.md` |
| D | solana_data_source_feasibility.json | `reports/lp_solana_connector_design/20260603_080347/solana_data_source_feasibility.json` |
| E | METEORA_DLMM_CONNECTOR_DESIGN_CN.md | `reports/lp_solana_connector_design/20260603_080347/METEORA_DLMM_CONNECTOR_DESIGN_CN.md` |
| E | meteora_dlmm_connector_design.json | `reports/lp_solana_connector_design/20260603_080347/meteora_dlmm_connector_design.json` |
| F | ORCA_WHIRLPOOL_CONNECTOR_DESIGN_CN.md | `reports/lp_solana_connector_design/20260603_080347/ORCA_WHIRLPOOL_CONNECTOR_DESIGN_CN.md` |
| F | orca_whirlpool_connector_design.json | `reports/lp_solana_connector_design/20260603_080347/orca_whirlpool_connector_design.json` |
| G | RAYDIUM_CONNECTOR_DESIGN_CN.md | `reports/lp_solana_connector_design/20260603_080347/RAYDIUM_CONNECTOR_DESIGN_CN.md` |
| G | raydium_connector_design.json | `reports/lp_solana_connector_design/20260603_080347/raydium_connector_design.json` |
| H | SOLANA_LP_SCHEMA_PROPOSAL_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_LP_SCHEMA_PROPOSAL_CN.md` |
| H | solana_lp_schema_proposal.json | `reports/lp_solana_connector_design/20260603_080347/solana_lp_schema_proposal.json` |
| I | SOLANA_SURVIVAL_EV_MODEL_ADAPTATION_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_SURVIVAL_EV_MODEL_ADAPTATION_CN.md` |
| I | solana_survival_ev_model_adaptation.json | `reports/lp_solana_connector_design/20260603_080347/solana_survival_ev_model_adaptation.json` |
| J | SOLANA_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_10_20U_PROBE_PREFLIGHT_DESIGN_CN.md` |
| J | solana_10_20u_probe_preflight_design.json | `reports/lp_solana_connector_design/20260603_080347/solana_10_20u_probe_preflight_design.json` |
| K | SOLANA_CONNECTOR_IMPLEMENTATION_ROADMAP_CN.md | `reports/lp_solana_connector_design/20260603_080347/SOLANA_CONNECTOR_IMPLEMENTATION_ROADMAP_CN.md` |
| K | solana_connector_implementation_roadmap.json | `reports/lp_solana_connector_design/20260603_080347/solana_connector_implementation_roadmap.json` |
| L | FINAL_VERDICT.json | `reports/lp_solana_connector_design/20260603_080347/FINAL_VERDICT.json` |
| L | ONEPAGE_CN.md | `reports/lp_solana_connector_design/20260603_080347/ONEPAGE_CN.md` |
| L | ARTIFACT_INDEX.md | `reports/lp_solana_connector_design/20260603_080347/ARTIFACT_INDEX.md` |

## 本阶段新增测试

- `tests/test_lp_solana_connector_design_v1_readonly.py` (待 Stage M 写)

## 引用上游 artifacts

### Multichain upstream
- `reports/lp_multichain_survival_ev/20260603_051605/FINAL_VERDICT.json` (recommended next stage)
- `reports/lp_multichain_survival_ev/20260603_051605/ONEPAGE_CN.md`
- `reports/lp_multichain_survival_ev/20260603_051605/ARTIFACT_INDEX.md`
- `reports/lp_multichain_survival_ev/20260603_051605/survival_horizon_ev_model.json`
- `reports/lp_multichain_survival_ev/20260603_051605/lp_candidate_scoring.json`

### Base 10U probe upstream
- `reports/lp_base_10u_probe_execution_script_build/20260602_135824/FINAL_VERDICT.json`
- `reports/lp_base_probe_execution_spec_review/20260602_133221/FINAL_VERDICT.json`

### Docs
- `docs/LPBOT_RESEARCH_STATUS_CN.md`
- `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md`

## 引用源码（未修改）

- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines; v2 line 974 raise 保留)
- 所有 EVM V3 multichain discovery / probe / scoring scripts (4 new files from upstream stage)
