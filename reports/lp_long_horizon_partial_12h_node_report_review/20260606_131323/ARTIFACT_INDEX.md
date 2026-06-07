# ARTIFACT INDEX — 12h Partial Node Report Review V1

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`
- 12h gate: **PASS** (12h pipeline stable, r0 phase data still placeholder)
- 12h review status: **PASS** (review pass) + r1_upgrade_required=true

## 1. Output files (in `reports/lp_long_horizon_partial_12h_node_report_review/20260606_131323/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) — 12h deliverable + data_dir + finalize 全部 audit |
| 2 | `INPUT_EVIDENCE_AUDIT.json` | 输入证据审计 (JSON) |
| 3 | `WHAT_12H_PROVED_CN.md` | 12h 证明 (8 项) — pipeline stability + safety + auto_advance LOCKED |
| 4 | `WHAT_12H_PROVED.json` | 12h 证明 (JSON) |
| 5 | `WHAT_12H_DID_NOT_PROVE_CN.md` | 12h 未证明 (8 项) — EV / fee accrual / range-tick-bin / full coverage |
| 6 | `WHAT_12H_DID_NOT_PROVE.json` | 12h 未证明 (JSON) |
| 7 | `COVERAGE_REVIEW_CN.md` | Coverage 3-level (chain/dex/pool) + data layer readiness |
| 8 | `COVERAGE_REVIEW.json` | Coverage review (JSON) |
| 9 | `FEE_ESTIMATION_REVIEW_CN.md` | Fee 估算大白话 + V3/CLMM/DLMM/CPMM 解释 + r1 升级需要 |
| 10 | `FEE_ESTIMATION_REVIEW.json` | Fee estimation review (JSON) |
| 11 | `CANDIDATE_REVIEW_AUDIT_CN.md` | Candidate 4 分类 + missing 5 field groups + global_lp_rejected 解释 |
| 12 | `CANDIDATE_REVIEW_AUDIT.json` | Candidate review audit (JSON) |
| 13 | `R0_TO_R1_DATA_UPGRADE_PLAN_CN.md` | R1 目标 (5+1+1) + R1 不做 + R1 启动前必经步骤 |
| 14 | `R0_TO_R1_DATA_UPGRADE_PLAN.json` | R0 → R1 upgrade plan (JSON) |
| 15 | `NEXT_STAGE_DECISION_CN.md` | 4-stage 评估 + 决策规则 + R1 启动前必经步骤 |
| 16 | `NEXT_STAGE_DECISION.json` | Next stage decision (JSON) |
| 17 | `FINAL_VERDICT.json` | Final verdict (status=PASS, recommended=R1) |
| 18 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 19 | `ARTIFACT_INDEX.md` | 本文件 |

## 2. Test file (in `tests/`)

| File | 描述 |
|---|---|
| `tests/test_lp_long_horizon_partial_12h_node_report_review_v1.py` | ≥ 6 测试, 12h pass ≠ edge_proven / fee_proxy_only / candidate_decision_unreliable / global_lp_rejected=false / no probe / final verdict allowed next stages only |

## 3. Stage H 12h 之前的 deliverable 全部仍 intact

| File | 路径 |
|---|---|
| 12h node report (CN) | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/12H_NODE_REPORT_CN.md` |
| 12h coverage manifest | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/coverage_manifest.json` |
| 12h fee estimation basis | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/fee_estimation_basis.json` |
| 12h candidate review | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/candidate_review.json` |
| 12h next node decision | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/next_node_decision.json` |
| 12h ARTIFACT_INDEX | `reports/lp_long_horizon_readonly_12h_node_report/20260606_131323/ARTIFACT_INDEX.md` |
| 12h request FINAL_VERDICT | `reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/FINAL_VERDICT.json` |
| 12h run FINAL_VERDICT (auto) | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/FINAL_VERDICT.json` |
| 12h data dir (12 ckpts) | `data/lp_long_horizon/20260606_131323/` |

## 4. 12h 关键字段 (LOCKED, 12h review 期间 + R1 期间)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `global_lp_rejected` | `false` |
| `actual_fee_data_available` | `false` |
| `fee_proxy_only` | `true` |
| `candidate_decision_reliable` | `false` |
| `preflight_candidate_count` | 0 |
| `watchlist_count` | 0 |
| `data_insufficient_count` | 53 |
| `reject_count` | 0 |
| `r1_upgrade_required` | `true` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `send_hard_disable_still_active` | `true` |

## 5. 严禁 (12h review 期间 + 后续 R1 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `can_run_probe_now=false`
- ❌ **不** 翻 `tiny_canary_allowed=no`
- ❌ **不** 翻 `edge_proven=no`
- ❌ **不** mint 实际 LP NFT 仓位 (R1 仅升级 data layer)

## 6. 4 allowed next stages (per FINAL_VERDICT)

1. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1` (推荐 per spec 规则)
2. `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (不推荐, 12h 仍 r0)
3. `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (不推荐, Base 仍 403)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (备选)

## 7. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_STAGE_SUPERVISOR_FINALIZE_FIX_V1` | done | supervisor finalize 4 Python heredoc lowercase bool bug |
| `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1` | done | universe 33 → 72 (8 protocols, 3 chains); 23 池 not observable |
| `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1` | done | 4 EVM/BSC adapter + 1 Meteora verify |
| `LP_LONG_HORIZON_COLLECTOR_RPC_REACHABILITY_AND_ADAPTER_SMOKE_FIX_V1` | done | rpc_registry.py + 13 → 49 observable; Base 不可达 |
| `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1` | done | 启动 12h partial (53 池) via nohup; checkpoint 1/12 ok |
| `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (Stage H auto) | done | 12h 跑通, 12/12 ok, gate PASS, finalize PASS |
| `LP_LONG_HORIZON_READONLY_12H_NODE_REPORT_REVIEW_V1` (Stage H node report) | done | 12h node report + 4 deliverable (coverage_manifest / fee_estimation_basis / candidate_review / next_node_decision) |
| **`LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`** (本 stage) | **done** | **12h review 跑完, 8/8 deliverables 写完, FINAL_VERDICT = PASS + recommended=R1** |
| 下一 stage (user decide) | pending | 4 allowed next stages, **推荐 R1** |
