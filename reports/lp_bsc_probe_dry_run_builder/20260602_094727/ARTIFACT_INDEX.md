# Artifact Index — `20260602_094727`

Stage: `LP_BSC_10_20U_PROBE_DRY_RUN_BUILDER_V1`
Status: **PASS**
recommended_next_stage: `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1`

## 报告文件

| 文件 | 用途 |
|---|---|
| `FINAL_VERDICT.json` | 顶层 verdict |
| `ONEPAGE_CN.md` | 单页总览 |
| `INPUT_EVIDENCE_AUDIT_CN.md` / `input_evidence_audit.json` | Phase B — 10 份上游输入逐项确认 |
| `BSC_DRY_RUN_CANDIDATE_FREEZE_CN.md` / `bsc_dry_run_candidate_freeze.json` | Phase C — 候选池/资金/hold 参数冻结 |
| `BSC_DRY_RUN_POOL_STATE_REFRESH_CN.md` / `bsc_dry_run_pool_state_refresh.json` | Phase D — slot0/liquidity/decimals/QuoterV2 quote (read-only) |
| `BSC_TICK_RANGE_PROPOSAL_CN.md` / `bsc_tick_range_proposal.json` | Phase E — narrow/medium/wide 三档；推荐 medium |
| `BSC_TOKEN_AMOUNT_CALCULATION_CN.md` / `bsc_token_amount_calculation.json` | Phase F — 10U/20U 的 amount0/amount1 + amountMin |
| `BSC_UNSIGNED_TX_PACKAGE_CN.md` / `bsc_unsigned_tx_package.json` | Phase G — mint / approve / decrease / collect / revoke / swap-back calldata draft（**不签名/不发送/不 emit bytes**） |
| `BSC_DRY_RUN_GAS_ESTIMATE_FEASIBILITY_CN.md` / `bsc_dry_run_gas_estimate_feasibility.json` | Phase H — 静态 gas units + 4 个 gas_cost 场景 + per-session ceiling |
| `BSC_PROBE_MANUAL_APPROVAL_CHECKPOINT_CN.md` / `bsc_probe_manual_approval_checkpoint.json` | Phase I — 唯一允许的审批短语 + 校验正则 + 禁止短语 |

## 上游引用

- 直接上游：`reports/lp_bsc_probe_preflight_review/20260602_092319/`（status PASS, recommended_next_stage 即本阶段）
- 经济数据上游：`reports/lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633/`

## 工具脚本

本阶段不引入新的 production 脚本。所有产物由 ad-hoc 只读 `eth_call` + 离线计算产出。
下一阶段 `LP_BSC_10_20U_PROBE_WALLET_ADDRESS_DRY_RUN_V1` 才会新增 `scripts/lp_bsc_10_20u_probe_wallet_address_dry_run_v1_readonly.py`。

## 测试

`tests/test_lp_bsc_probe_dry_run_builder_v1_readonly.py` — Phase K 添加。
