# Artifact Index — `20260602_105654`

Stage: `LP_EVM_WALLET_ADDRESS_CROSSCHAIN_DRY_RUN_ROUTER_V1`
Status: **PASS**
recommended_next_stage: `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1`

## 报告文件

| 文件 | Phase | 用途 |
|---|---|---|
| `FINAL_VERDICT.json` | J | 顶层 verdict |
| `ONEPAGE_CN.md` | J | 单页总览 |
| `INPUT_EVIDENCE_AUDIT_CN.md` / `input_evidence_audit.json` | B | 18 份上游输入逐项确认 |
| `EVM_WALLET_CHAIN_RPC_READINESS_CN.md` / `evm_wallet_chain_rpc_readiness.json` | C | Base + BSC RPC chainId/blockNumber 只读检查（host_hash 脱敏） |
| `EVM_WALLET_CROSSCHAIN_BALANCE_AUDIT_CN.md` / `evm_wallet_crosschain_balance_audit.json` / `.csv` | D | wallet 跨链余额 + USD anchor (WETH/cbBTC/WBNB) |
| `EVM_WALLET_CROSSCHAIN_ALLOWANCE_AUDIT_CN.md` / `evm_wallet_crosschain_allowance_audit.json` / `.csv` | E | NPM allowance 只读 |
| `BSC_WALLET_READINESS_CHECK_CN.md` / `bsc_wallet_readiness_check.json` | F | BSC 候选 blocked by no BSC funds |
| `BASE_CANDIDATE_FROM_EXISTING_ARTIFACTS_CN.md` / `base_candidate_from_existing_artifacts.json` / `.csv` | G | 5 个 Base V3 候选 + 钱包 token 匹配 |
| `CROSSCHAIN_DRY_RUN_ROUTE_DECISION_CN.md` / `crosschain_dry_run_route_decision.json` | H | 路由决策 = Base |
| `BASE_10_20U_PROBE_PREFLIGHT_REVIEW_NEXT_SPEC_CN.md` / `base_10_20u_probe_preflight_review_next_spec.json` | I | 下一阶段 spec |

## 上游引用

| 上游 | 路径 |
|---|---|
| BSC dry-run builder | `reports/lp_bsc_probe_dry_run_builder/20260602_094727` (status PASS) |
| BSC preflight review | `reports/lp_bsc_probe_preflight_review/20260602_092319` (status PASS) |
| BSC recovery + economics | `reports/lp_bsc_fee_velocity_recovery_probe_preflight/20260602_060633` (status PASS) |
| Base precise quote | `reports/lp_precise_quote/20260601_120001` |
| Base v3 tick liquidity | `reports/lp_v3_tick_liquidity_fix/20260601_132644` |
| Base real cost model | `reports/lp_real_cost_model/20260601_141103` |
| Base real fee accrual | `reports/lp_real_fee_accrual/20260601_143401` |
| Base universe normalized | `reports/lp_universe_scope_audit/20260601_154136` |

## 工具脚本

本阶段不引入新的 production 脚本。所有产物通过 ad-hoc 只读 `eth_call` + 离线计算 + 既有 CSV 解析生成。
下一阶段 `LP_BASE_10_20U_PROBE_DRY_RUN_BUILDER_V1` 将类比 BSC 阶段，亦不引入执行脚本。

## 测试

`tests/test_lp_evm_wallet_crosschain_dry_run_router_v1_readonly.py` —— Phase K 添加。
