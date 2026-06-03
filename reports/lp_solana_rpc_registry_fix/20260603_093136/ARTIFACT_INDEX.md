# Artifact Index — LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1

- run_id: `20260603_093136`
- report_dir: `reports/lp_solana_rpc_registry_fix/20260603_093136/`

## 本阶段产物

| phase | artifact | 路径 |
|---|---|---|
| A | STAGE_A_WORKSPACE_SAFETY.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/STAGE_A_WORKSPACE_SAFETY.md` |
| B | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/INPUT_EVIDENCE_AUDIT_CN.md` |
| B | input_evidence_audit.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/input_evidence_audit.json` |
| C | SOLANA_PROGRAM_ID_OFFICIAL_SOURCE_DISCOVERY_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_PROGRAM_ID_OFFICIAL_SOURCE_DISCOVERY_CN.md` |
| C | solana_program_id_official_source_discovery.csv | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_official_source_discovery.csv` |
| C | solana_program_id_official_source_discovery.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_official_source_discovery.json` |
| D | (registry v2 CSV) | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.csv` |
| D | (registry v2 JSON) | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` |
| D | (registry v2 design) | see above (per spec only CSV + JSON required; not separate md required) |
| E | SOLANA_PROGRAM_ID_ONCHAIN_VERIFICATION_V2_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_PROGRAM_ID_ONCHAIN_VERIFICATION_V2_CN.md` |
| E | solana_program_id_onchain_verification_v2.csv | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_onchain_verification_v2.csv` |
| E | solana_program_id_onchain_verification_v2.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_onchain_verification_v2.json` |
| F | SOLANA_GPA_SMOKE_V2_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_GPA_SMOKE_V2_CN.md` |
| F | solana_gpa_smoke_v2.csv | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_gpa_smoke_v2.csv` |
| F | solana_gpa_smoke_v2.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_gpa_smoke_v2.json` |
| G | METEORA_DLMM_REGISTRY_READINESS_V2_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/METEORA_DLMM_REGISTRY_READINESS_V2_CN.md` |
| G | meteora_dlmm_registry_readiness_v2.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/meteora_dlmm_registry_readiness_v2.json` |
| H | SOLANA_P1_P2_REGISTRY_READINESS_V2_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_P1_P2_REGISTRY_READINESS_V2_CN.md` |
| H | solana_p1_p2_registry_readiness_v2.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_p1_p2_registry_readiness_v2.json` |
| I | SOLANA_RPC_REGISTRY FIX_NEXT_STAGE_DECISION_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/SOLANA_RPC_REGISTRY FIX_NEXT_STAGE_DECISION_CN.md` |
| I | solana_rpc_registry_fix_next_stage_decision.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_rpc_registry_fix_next_stage_decision.json` |
| K | FINAL_VERDICT.json | `reports/lp_solana_rpc_registry_fix/20260603_093136/FINAL_VERDICT.json` |
| K | ONEPAGE_CN.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/ONEPAGE_CN.md` |
| K | ARTIFACT_INDEX.md | `reports/lp_solana_rpc_registry_fix/20260603_093136/ARTIFACT_INDEX.md` |

## 本阶段新增代码

- `scripts/lp_solana_program_id_onchain_verifier_v1.py` (new; stdlib only; supports both `verify` and `gpa` modes via argv dispatch)

## 本阶段新增测试

- `tests/test_lp_solana_rpc_registry_fix_repeat_v1.py` (待 Stage L 写)

## 引用上游 artifacts

### Solana registry upstream
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/FINAL_VERDICT.json`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/ONEPAGE_CN.md`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_RPC_READINESS_MATRIX_CN.md`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_rpc_readiness_matrix.json`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA PROTOCOL_REGISTRY_SEED_CN.md`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_protocol_registry_seed.json`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_PROGRAM_ID_VERIFICATION_CN.md`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_program_id_verification.json`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/SOLANA_READONLY_RPC_REGISTRY_NEXT_STAGE_DECISION_CN.md`
- `reports/lp_solana_readonly_rpc_registry/20260603_084054/solana_readonly_rpc_registry_next_stage_decision.json`

### Solana connector design upstream
- `reports/lp_solana_connector_design/20260603_080347/FINAL_VERDICT.json`

## 引用源码（未修改）

- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines; v2 line 974 raise 保留)
- `scripts/lp_solana_readonly_rpc_registry_v1.py` (上一轮; stdlib only)
- `scripts/lp_solana_program_id_onchain_verifier_v1.py` (本轮 new; stdlib only)
