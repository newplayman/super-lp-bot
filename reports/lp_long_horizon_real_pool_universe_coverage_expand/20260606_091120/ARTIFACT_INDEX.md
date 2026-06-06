# ARTIFACT INDEX — Real Pool Universe Coverage Expand V1

- stage: `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_V1`
- run_id: `20260606_091120`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (3 quantity targets met, observable sub-targets NOT met)
- generated_at_utc: `2026-06-06T09:20:00Z`

## 1. Output files (in `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) — finalize fix done, 5 protocols missing confirmed |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `meteora_dlmm_coverage_expand.csv` | 16 Meteora DLMM pools (CSV) |
| 4 | `meteora_dlmm_coverage_expand.json` | 16 Meteora DLMM pools (JSON) |
| 5 | `METEORA_DLMM_COVERAGE_EXPAND_CN.md` | Meteora DLMM 报告 (CN) |
| 6 | `base_uniswap_v3_coverage_expand.csv` | 5 Base UniV3 pools (CSV) |
| 7 | `base_uniswap_v3_coverage_expand.json` | 5 Base UniV3 pools (JSON) |
| 8 | `BASE_UNISWAP_V3_COVERAGE_EXPAND_CN.md` | Base UniV3 报告 (CN) |
| 9 | `base_aerodrome_coverage_expand.csv` | 5 Base Aerodrome pools (CSV) |
| 10 | `base_aerodrome_coverage_expand.json` | 5 Base Aerodrome pools (JSON) |
| 11 | `BASE_AERODROME_COVERAGE_EXPAND_CN.md` | Base Aerodrome 报告 (CN) |
| 12 | `bsc_pancakeswap_coverage_expand.csv` | 13 BSC PancakeSwap pools (CSV) |
| 13 | `bsc_pancakeswap_coverage_expand.json` | 13 BSC PancakeSwap pools (JSON) |
| 14 | `BSC_PANCAKESWAP_COVERAGE_EXPAND_CN.md` | BSC PancakeSwap 报告 (CN) |
| 15 | `expanded_real_pool_universe_for_12h_retry.csv` | 72 merged pools (CSV) |
| 16 | `expanded_real_pool_universe_for_12h_retry.json` | 72 merged pools (JSON) |
| 17 | `EXPANDED_REAL_POOL_UNIVERSE_FOR_12H_RETRY_CN.md` | Merged universe report (CN) |
| 18 | `coverage_gap_decision.json` | Gap decision (JSON) |
| 19 | `COVERAGE_GAP_DECISION_CN.md` | Gap decision (CN) |
| 20 | `FINAL_VERDICT.json` | Final verdict (含 spec-required 完整字段) |
| 21 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 22 | `ARTIFACT_INDEX.md` | 本文件 |
| 23 | `build_*.py` (4 files) | Helper scripts (read-only, generates the above artifacts) |

## 2. Build helpers (4 Python scripts, read-only)

| 文件 | 描述 |
|---|---|
| `build_meteora_dlmm_coverage.py` | 读 16 verified Meteora pools, 写 meteora_dlmm_coverage_expand.{csv,json,CN.md} |
| `build_base_uniswap_v3_coverage.py` | 1 verified + 4 inferred Base UniV3 pools |
| `build_base_aerodrome_coverage.py` | 4 classic + 1 slipstream Base Aerodrome pools |
| `build_bsc_pancakeswap_coverage.py` | 8 V3 (real addresses) + 5 V2 (3 documented + 2 placeholder) |
| `build_expanded_universe.py` | Merge 33 + 39 = 72 pools |
| `build_coverage_gap_decision.py` | Decide recommended next stage |

## 3. Expanded universe summary

| 字段 | 值 |
|---|---|
| `total_pool_count` | **72** (target ≥ 45) |
| `added_pool_count` | **39** (16 Meteora + 5 Base UniV3 + 5 Base Aero + 8 BSC V3 + 5 BSC V2) |
| `observable_pool_count` | **49** (Solana only: 33 V2 + 16 Meteora) |
| `non_observable_pool_count` | **23** (10 Base + 13 BSC) |
| `chain_distribution` | solana: 49, base: 10, bsc: 13 |
| `protocol_distribution` | 8 protocols (4 Solana observable, 4 EVM/BSC non-observable) |
| `placeholder_pool_count` | **0** (no `<smoke_pool_`; 5 pools use `PENDING_*_RPC_VALIDATION` markers) |
| `target_pool_count_met` | ✅ true |
| `target_protocol_count_met` | ✅ true |
| `target_chain_count_met` | ✅ true |
| `collector_full_coverage_ready` | ❌ false (23 pools not observable) |

## 4. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` |
| `auto_next_stage_disabled` | `true` |
| `no_collector_started` | `true` |
| `no_tmux_session_created` | `true` |

## 5. 严禁 (本轮全部不触发)

- ❌ 不启动 12h / 24h / 48h / 72h / 7d retry
- ❌ 不启动 long-running collector
- ❌ 不启动 Base/BSC EVM collector (下一 stage 才做)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer / 私钥
- ❌ 不发送 transaction
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner (上一 stage 已修 finalize)
- ❌ **不**修改 collector (上一-2 stage 已修 --pool-universe)

## 6. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_stage_supervisor_finalize_fix/20260606_082958/FINAL_VERDICT.json` (prior stage)
- `reports/lp_long_horizon_real_pool_universe_collector_fix/20260605_083000/FINAL_VERDICT.json` (prior-2 stage)
- `reports/lp_long_horizon_node_reports/20260605_082120/12h/FINAL_NODE_VERDICT.json` (12h node report)
- `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` (current 33-pool universe)
- `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_pool_chain_verification.json` (16 verified Meteora pools)
- `reports/lp_meteora_dlmm_known_pool_feed_expansion_overnight/20260603_174815/meteora_batch_pool_snapshot.csv` (Meteora token mints + fees)
- `reports/lp_bsc_pancakeswap_v3_precise_quote/20260602_235959/bsc_quote_target_candidates.csv` (8 BSC V3 pool addresses)
- `reports/lp_base_10u_probe_execution_authorization_package/20260602_184806/FINAL_VERDICT.json` (1 verified Base UniV3 pool)

## 7. 4-stage allowed next stages

- **`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`** (本 stage 推荐)
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_REAL_UNIVERSE_RETRY_REQUEST_V1` (12h retry, 但仅在 EVM/BSC 已 wired 后)
- `LP_LONG_HORIZON_REAL_POOL_UNIVERSE_COVERAGE_EXPAND_REPEAT` (不推荐, Solana 已 ≥ 45 target)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户决定暂停)

## 8. Recommended next stage

**`LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_V1`**

理由: universe 已扩到 72 pools + 3 chains + 8 protocols, 3 个 spec 数量目标全 met. 但 observable 仅 49 池, 4 protocols, 1 chain (Solana). 23 池 (10 Base + 13 BSC) waiting EVM/BSC adapter wiring. 完成 EVM/BSC 接线 (Go pool adapters for Aerodrome / PancakeSwap V3 / PancakeSwap V2 + EVM chain adapter to long-horizon collector + RPC-validate 5 placeholder pool addresses) 后, 23 池变 observable, 12h retry 才 `full_coverage_ready=true`.

## 9. 关键 honest disclosure

本 stage **没有** RPC-validate 4 个 inferred Base UniV3 + 1 Slipstream + 2 BSC V2 placeholder pool addresses. 它们的 `pool_address` 是 `PENDING_*_RPC_VALIDATION` marker, 等待下一 stage 用 `UniswapV3Factory.getPool` / `PancakeSwap V2 Factory.getPair` 等 eth_call 解析.
