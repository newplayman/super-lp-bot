# Artifact Index — LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1

- run_id: `20260604_034503`
- branch: `feat/supabase-postgres-deployment`
- head_before: `9f0495a`

## 阶段 A — workspace safety

(无 artifact; 检查结果在 Stage B 中记录)

## 阶段 B — input evidence audit

| file | 描述 |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 上游 10 个 stage 证据审计 + V3 CL 累计 2/3 reject 总结 |
| `input_evidence_audit.json` | 审计结构化 (v3_cl_amm_cumulative) |

## 阶段 C — Raydium SDK source audit

| file | 描述 |
|---|---|
| `ORCA_WHIRLPOOL_SDK_SOURCE_AUDIT_CN.md` | 官方 source 审计 (GitHub + npm); read-only methods (PoolInfoLayout, getPdaTickArrayAddress, getDxByDxBaseIn, getDyByDxBaseIn) |
| `raydium_clmm_sdk_source_audit.json` | source URLs, package versions, PoolState fields, read_only_functions list |

## 阶段 D — isolated SDK install

| file | 描述 |
|---|---|
| `ORCA_WHIRLPOOL_SDK_PACKAGE_AUDIT_CN.md` | npm install 验证, SOL/USDC 0.01% pool probe, GeckoTerminal dex label caveat (raydium vs raydium-clmm) |
| `raydium_clmm_sdk_package_audit.json` | install 状态, read_only decode proof |

## 阶段 E — candidate source collection

| file | 描述 |
|---|---|
| `raydium_clmm_candidate_source_collection.py` | 收集脚本 (GeckoTerminal raydium-clmm + DexScreener) |
| `raydium_clmm_candidate_source_collection.json` | 107 unique candidates |
| `raydium_clmm_candidate_source_collection.csv` | CSV form |
| (CN summary integrated in Stage F file) | |

## 阶段 F — chain verify + dedupe

| file | 描述 |
|---|---|
| `raydium_clmm_pool_chain_verify.py` | getAccountInfo 验证脚本 |
| `raydium_clmm_pool_chain_verification.json` | 65/80 verified (15 owner_mismatch filtered) |
| `raydium_clmm_pool_chain_verification.csv` | CSV form |

## 阶段 G — pool account decode

| file | 描述 |
|---|---|
| `raydium_clmm_pool_decode_runner.js` | Node.js SDK decode runner (PoolInfoLayout) |
| `raydium_clmm_pool_snapshot.json` | 65 行 SDK decode 结果 |
| `raydium_clmm_pool_snapshot.csv` | CSV form |

## 阶段 H — tick array read/decode

| file | 描述 |
|---|---|
| `raydium_tick_array_decode_runner.js` | Tick array PDA derive + read |
| `raydium_tick_array_snapshot.json` | 195 行 (2/195 success) |
| `raydium_tick_array_snapshot.csv` | CSV form |

## 阶段 I — quote smoke

| file | 描述 |
|---|---|
| `raydium_clmm_quote_smoke_runner.js` | liquidity ratio heuristic quote |
| `raydium_clmm_quote_smoke.json` | 104 行 (50/53 quote-ready) |
| `raydium_clmm_quote_smoke.csv` | CSV form |

## 阶段 J — survival EV preview

| file | 描述 |
|---|---|
| `raydium_clmm_survival_ev_preview.py` | EV preview (heuristic 0.5%/day turnover; 25bps default fee; $0.008 cost) |
| `raydium_clmm_survival_ev_preview.json` | 8400 行 (50 × 6 × 7 × 4) |
| `raydium_clmm_survival_ev_preview.csv` | CSV form |

## 阶段 K — candidate decision

| file | 描述 |
|---|---|
| `ORCA_CANDIDATE_DECISION_CN.md` | 7 项判断 + spec rule_2 + user instruction → Raydium CPMM |
| `raydium_clmm_candidate_decision.json` | 决策结构化 (v3_cl_amm_cumulative: 3/3 reject) |

## 阶段 L — final verdict

| file | 描述 |
|---|---|
| `FINAL_VERDICT.json` | status=WARN, recommended_next_stage=LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1 |
| `ONEPAGE_CN.md` | 一页总结 (counts + finding + 3 V3 CL 对比) |
| `ARTIFACT_INDEX.md` | 本文件 |

## data/ 子目录

- `data/collection_summary.json`
- `data/chain_verify_summary.json`
- `data/decode_summary.json`
- `data/tick_array_summary.json`
- `data/quote_summary.json`
- `data/survival_ev_summary.json`

## 安全断言总览 (跨阶段)

| 阶段 | touched_trading_path | touched_wallet_tx_bridge_live_paper | keypair | signer | transaction |
|---|---|---|---|---|---|
| A–L | no | no | no | no | no |
