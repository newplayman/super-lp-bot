# Artifact Index — LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1

- run_id: `20260603_051605`
- report_dir: `reports/lp_multichain_survival_ev/20260603_051605/`

## 本阶段产物

| phase | artifact | 路径 |
|---|---|---|
| A | STAGE_A_WORKSPACE_SAFETY.md | `reports/lp_multichain_survival_ev/20260603_051605/STAGE_A_WORKSPACE_SAFETY.md` |
| B | INPUT_EVIDENCE_AUDIT_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/INPUT_EVIDENCE_AUDIT_CN.md` |
| B | input_evidence_audit.json | `reports/lp_multichain_survival_ev/20260603_051605/input_evidence_audit.json` |
| C | MULTICHAIN_DEX_UNIVERSE_PLAN_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/MULTICHAIN_DEX_UNIVERSE_PLAN_CN.md` |
| C | multichain_dex_universe_plan.json | `reports/lp_multichain_survival_ev/20260603_051605/multichain_dex_universe_plan.json` |
| C | multichain_dex_universe_plan.csv | `reports/lp_multichain_survival_ev/20260603_051605/multichain_dex_universe_plan.csv` |
| D | EVM_STANDARD_V3_MULTICHAIN_DISCOVERY_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/EVM_STANDARD_V3_MULTICHAIN_DISCOVERY_CN.md` |
| D | evm_standard_v3_multichain_discovery.csv | `reports/lp_multichain_survival_ev/20260603_051605/evm_standard_v3_multichain_discovery.csv` |
| D | evm_standard_v3_multichain_discovery.json | `reports/lp_multichain_survival_ev/20260603_051605/evm_standard_v3_multichain_discovery.json` |
| E | MULTICHAIN_POOL_READINESS_PROBE_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/MULTICHAIN_POOL_READINESS_PROBE_CN.md` |
| E | multichain_pool_readiness_probe.csv | `reports/lp_multichain_survival_ev/20260603_051605/multichain_pool_readiness_probe.csv` |
| E | multichain_pool_readiness_probe.json | `reports/lp_multichain_survival_ev/20260603_051605/multichain_pool_readiness_probe.json` |
| F | SURVIVAL_HORIZON_EV_MODEL_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/SURVIVAL_HORIZON_EV_MODEL_CN.md` |
| F | survival_horizon_ev_model.csv | `reports/lp_multichain_survival_ev/20260603_051605/survival_horizon_ev_model.csv` |
| F | survival_horizon_ev_model.json | `reports/lp_multichain_survival_ev/20260603_051605/survival_horizon_ev_model.json` |
| G | SURVIVAL_OUT_OF_RANGE_RISK_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/SURVIVAL_OUT_OF_RANGE_RISK_CN.md` |
| G | survival_out_of_range_risk.csv | `reports/lp_multichain_survival_ev/20260603_051605/survival_out_of_range_risk.csv` |
| G | survival_out_of_range_risk.json | `reports/lp_multichain_survival_ev/20260603_051605/survival_out_of_range_risk.json` |
| H | LP_CANDIDATE_SCORING_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/LP_CANDIDATE_SCORING_CN.md` |
| H | lp_candidate_scoring.csv | `reports/lp_multichain_survival_ev/20260603_051605/lp_candidate_scoring.csv` |
| H | lp_candidate_scoring.json | `reports/lp_multichain_survival_ev/20260603_051605/lp_candidate_scoring.json` |
| I | MULTICHAIN_PROBE_ROUTE_DECISION_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/MULTICHAIN_PROBE_ROUTE_DECISION_CN.md` |
| I | multichain_probe_route_decision.json | `reports/lp_multichain_survival_ev/20260603_051605/multichain_probe_route_decision.json` |
| J | NEXT_STAGE_DECISION_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/NEXT_STAGE_DECISION_CN.md` |
| J | next_stage_decision.json | `reports/lp_multichain_survival_ev/20260603_051605/next_stage_decision.json` |
| K | FINAL_VERDICT.json | `reports/lp_multichain_survival_ev/20260603_051605/FINAL_VERDICT.json` |
| K | ONEPAGE_CN.md | `reports/lp_multichain_survival_ev/20260603_051605/ONEPAGE_CN.md` |
| K | ARTIFACT_INDEX.md | `reports/lp_multichain_survival_ev/20260603_051605/ARTIFACT_INDEX.md` |

## 本阶段新增代码

- `scripts/lp_evm_standard_v3_multichain_discovery_v1_readonly.py` (P0 6 chain × N pair × 4 fee getPool)
- `scripts/lp_evm_v3_pool_readiness_probe_v1_readonly.py` (slot0 + liquidity + gas + quoter attempt)
- `scripts/lp_survival_horizon_ev_model_v1_readonly.py` (5 scen × 6 notional × 9 hold × 74 pool)
- `scripts/lp_survival_out_of_range_risk_v1_readonly.py` (Gaussian half-normal OOR risk)
- `scripts/lp_candidate_scoring_v1_readonly.py` (10-dim weighted score)

## 本阶段新增测试

- `tests/test_lp_multichain_survival_ev_v1_readonly.py` (待 Stage L 写)

## 引用上游 artifacts

### Base 10U probe upstream
- `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/FINAL_VERDICT.json` (NO_GO)
- `reports/lp_base_10u_probe_monitor_finalize/20260603_040018/BASE_10U_PROBE_GO_NOGO_REVIEW_CN.md`
- `reports/lp_base_10u_probe_overnight_armed_runner/20260602_193517/monitor/readiness_timeseries.csv` (47 checkpoints 历史 tick drift 锚点)

### EVM wallet / BSC fee velocity / universe audit
- `reports/lp_evm_wallet_crosschain_dry_run_router/20260602_105654/FINAL_VERDICT.json`
- `reports/lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633/FINAL_VERDICT.json`
- `reports/lp_universe_scope_audit/20260601_154136/FINAL_VERDICT.json`
- `reports/lp_evm_standard_v3_discovery/20260602_000000/FINAL_VERDICT.json`

### Docs
- `docs/LPBOT_RESEARCH_STATUS_CN.md`
- `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md`

## 引用源码（未修改）

- `scripts/lp_base_10u_probe_executor_v2.py` (992 lines; v2 line 974 raise 保留)
- `scripts/lp_base_10u_probe_armed_runner_v1.py` (armed runner v1; execute-armed 硬退出)
- `scripts/lp_base_10u_probe_readiness_monitor_v1.py` (monitor; --finalize 验证)
- `scripts/lp_evm_standard_v3_multichain_discovery_v1_readonly.py` (new)
- `scripts/lp_evm_v3_pool_readiness_probe_v1_readonly.py` (new)
- `scripts/lp_survival_horizon_ev_model_v1_readonly.py` (new)
- `scripts/lp_survival_out_of_range_risk_v1_readonly.py` (new)
- `scripts/lp_candidate_scoring_v1_readonly.py` (new)
