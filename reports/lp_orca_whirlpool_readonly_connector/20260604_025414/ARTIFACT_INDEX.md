# Artifact Index — LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1

- run_id: `20260604_025414`
- branch: `feat/supabase-postgres-deployment`
- head_before: `22d2941`

## 阶段 A — workspace safety

(无 artifact; 检查结果在 Stage B 中记录)

## 阶段 B — input evidence audit

| file | 描述 |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 上游 10 个 stage 证据审计 |
| `input_evidence_audit.json` | 审计结构化 (previous_meteora_targeted_stage, orca_whirlpool_program_id) |

## 阶段 C — Orca SDK source audit

| file | 描述 |
|---|---|
| `ORCA_WHIRLPOOL_SDK_SOURCE_AUDIT_CN.md` | 官方 source 审计 (GitHub + npm); 9 个 read-only methods 列出 |
| `orca_whirlpool_sdk_source_audit.json` | source URLs, package versions, read_only_methods list |

## 阶段 D — isolated SDK install

| file | 描述 |
|---|---|
| `ORCA_WHIRLPOOL_SDK_PACKAGE_AUDIT_CN.md` | npm install 验证, 4 SOL/USDC pool probe, Orca official API 14983 池 |
| `orca_whirlpool_sdk_package_audit.json` | install 状态, read_only probe results, Orca API 14983 池 |

## 阶段 E — candidate source collection

| file | 描述 |
|---|---|
| `orca_candidate_source_collection.py` | 收集脚本 (Orca official + DexScreener) |
| `orca_candidate_source_collection.json` | 15002 candidate (14983 + 19) |
| `orca_candidate_source_collection.csv` | CSV form |
| `ORCA_CANDIDATE_SOURCE_COLLECTION_CN.md` | 来源策略 + 75 selected for chain verify |

## 阶段 F — chain verify + dedupe

| file | 描述 |
|---|---|
| `orca_pool_chain_verify.py` | getAccountInfo 验证脚本 (8 worker parallel) |
| `orca_pool_chain_verification.json` | 75 行 (100% verify) |
| `orca_pool_chain_verification.csv` | CSV form |
| `ORCA_POOL_CHAIN_VERIFICATION_CN.md` | 链上验证报告 + 653 bytes data_len finding |

## 阶段 G — Whirlpool account decode

| file | 描述 |
|---|---|
| `orca_whirlpool_pool_decode_runner.js` | Node.js SDK decode runner |
| `orca_whirlpool_pool_snapshot.json` | 75 行 SDK decode 结果 (feeRate 1-200bps) |
| `orca_whirlpool_pool_snapshot.csv` | CSV form |
| `ORCA_WHIRLPOOL_POOL_SNAPSHOT_CN.md` | 75 池 fee 分布 + tick_spacing 分布 + 流动性 top 10 |

## 阶段 H — tick array read/decode

| file | 描述 |
|---|---|
| `orca_tick_array_decode_runner.js` | Tick array PDA derive + read (3 arrays per pool) |
| `orca_tick_array_snapshot.json` | 225 行 (4/225 success) |
| `orca_tick_array_snapshot.csv` | CSV form |
| `ORCA_TICK_ARRAY_SNAPSHOT_CN.md` | LAZY init finding; pool-level liquidity proxy |

## 阶段 I — quote smoke

| file | 描述 |
|---|---|
| `orca_quote_smoke_runner.js` | swapInstructions quote-only mode (10/20 USD) |
| `orca_quote_smoke.json` | 126 行 (10/75 quote-ready, 106/126 429-failed) |
| `orca_quote_smoke.csv` | CSV form |
| `ORCA_QUOTE_SMOKE_CN.md` | 10 quote-ready 池 + 真实 fee data + 429 limitation |

## 阶段 J — survival EV preview

| file | 描述 |
|---|---|
| `orca_survival_ev_preview.py` | EV preview (heuristic 0.5%/day turnover; Orca cost $0.006) |
| `orca_survival_ev_preview.json` | 1680 行 (10 × 6 × 7 × 4) |
| `orca_survival_ev_preview.csv` | CSV form |
| `ORCA_SURVIVAL_EV_PREVIEW_CN.md` | 29 positive cells all zero_il_lvr; best +$0.106 |

## 阶段 K — candidate decision

| file | 描述 |
|---|---|
| `ORCA_CANDIDATE_DECISION_CN.md` | 7 项判断 + spec rule_2 → Raydium CLMM |
| `orca_candidate_decision.json` | 决策结构化 (reasons[], rejected_alternatives) |

## 阶段 L — final verdict

| file | 描述 |
|---|---|
| `FINAL_VERDICT.json` | status=WARN, recommended_next_stage=LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1 |
| `ONEPAGE_CN.md` | 一页总结 (counts + finding + V1/V8 对比) |
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
