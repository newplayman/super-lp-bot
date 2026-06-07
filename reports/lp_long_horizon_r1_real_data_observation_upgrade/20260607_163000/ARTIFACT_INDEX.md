# ARTIFACT INDEX — R1 Real-Data Observation Upgrade V1

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T17:10:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`
- r1_smoke_status: **PASS**

## 1. Output files (in `reports/lp_long_horizon_r1_real_data_observation_upgrade/20260607_163000/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `R1_REAL_DATA_SCHEMA_CN.md` | R1 schema 6 dimensions (CN) |
| 4 | `r1_real_data_schema.json` | R1 schema 6 dimensions (JSON) |
| 5 | `R1_COLLECTOR_ARCHITECTURE_CN.md` | R1 collector architecture (CN) |
| 6 | `r1_collector_architecture.json` | R1 collector architecture (JSON) |
| 7 | `R1_SHORT_SMOKE_RESULT_CN.md` | R1 smoke result (CN) |
| 8 | `r1_short_smoke_result.json` | R1 smoke result (JSON) |
| 9 | `R1_CANDIDATE_INTERPRETATION_CN.md` | R1 candidate interpretation (CN) |
| 10 | `r1_candidate_interpretation.json` | R1 candidate interpretation (JSON) |
| 11 | `R1_NEXT_STAGE_DECISION_CN.md` | R1 next-stage decision (CN) |
| 12 | `r1_next_stage_decision.json` | R1 next-stage decision (JSON) |
| 13 | `FINAL_VERDICT.json` | Final verdict (status=PASS, recommended=R1 12h) |
| 14 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 15 | `ARTIFACT_INDEX.md` | 本文件 |

## 2. R1 collector (in `scripts/`)

| File | 描述 |
|---|---|
| `scripts/lp_long_horizon_r1_real_data_collector_v1.py` | R1 real-data read-only collector (smoke), 6 dimensions fetch, fail-fast honest failure mode |

## 3. R1 smoke data dir (in `data/`)

| Path | 描述 |
|---|---|
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_pool_snapshot.csv` | 20 池 real pool snapshot (7 medium + 13 low) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_pool_snapshot.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_quote_snapshot.csv` | 120 rows (20 × 6 notional) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_quote_snapshot.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_fee_velocity.csv` | 100 rows (20 × 5 windows, 100 unavailable) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_fee_velocity.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_liquidity_distribution.csv` | 20 rows (7 low + 13 unavailable) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_liquidity_distribution.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_market_regime.csv` | 2 rows (solana + bsc, 真实 CoinGecko) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_market_regime.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_candidate_review.csv` | 20 rows (7 watchlist, 0 preflight, 0 data_insufficient) |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_candidate_review.json` | 同上 JSON |
| `data/lp_long_horizon_r1_smoke/20260607_163000/r1_smoke_summary.json` | 顶层 summary (selected_pool_count=20, etc.) |

## 4. Test file (in `tests/`)

| File | 描述 |
|---|---|
| `tests/test_lp_long_horizon_r1_real_data_observation_upgrade_v1.py` | ≥ 8 测试: r1 schema exists, r1 collector no placeholder fallback, no wallet/keypair/signer, no tx send, actual_fee_data_available remains false, fee_proxy_only true, candidate review fields exist, final verdict allowed next stages only |

## 5. R1 关键字段 (LOCKED, R1 期间)

| 字段 | 锁定值 |
|---|---|
| `r1_schema_ready` | `true` |
| `r1_collector_built` | `true` |
| `r1_short_smoke_ran` | `true` |
| `actual_fee_data_available` | `false` |
| `fee_proxy_only` | `true` (R1 ≠ actual fee) |
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `global_lp_rejected` | `false` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |

## 6. 严禁 (R1 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `can_run_probe_now=false` / `tiny_canary_allowed=no` / `edge_proven=no` / `actual_fee_data_available=false`
- ❌ **不** 修改 R0 collector / adapters
- ❌ **不** 修改 12h data dir
- ❌ **不** mint 实际 LP NFT 仓位 (R1 严格 read-only)

## 7. 4 allowed next stages (per FINAL_VERDICT)

1. `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1` (推荐, 5/5 spec rules match)
2. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` (R1 12h 跑出 fee/liquidity 问题时再考虑)
3. `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (Base 仍 403, 需换 env)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (备选)

## 8. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (12h) | done | 12h 跑通, 12/12 ckpt, r0 phase |
| `LP_LONG_HORIZON_READONLY_12H_NODE_REPORT_REVIEW_V1` | done | 12h node report + 4 deliverable |
| `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` | done | 12h review (53/53 data_insufficient, recommended=R1) |
| **`LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`** (本 stage) | **done** | **R1 schema 6 dim + R1 collector + R1 smoke (20 池, 6 dim row>0, 7 watchlist, 0 data_insufficient) + R1 推荐 R1 12h** |
| 下一 stage (user decide) | pending | 4 allowed, **推荐 R1 12h** |
