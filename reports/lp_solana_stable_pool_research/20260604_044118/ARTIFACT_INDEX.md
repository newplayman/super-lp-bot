# Artifact Index — LP_SOLANA_STABLE_POOL_RESEARCH_V1 (LP Research 收口)

- run_id: `20260604_044118`
- branch: `feat/supabase-postgres-deployment`
- head_before: `8b2562a`
- **this is the LP research 收口 stage (per spec rule_2 + 5/5 AMM reject)**

## 阶段 A — workspace safety

(无 artifact; 检查结果在 Stage B 中记录)

## 阶段 B — input evidence audit

| file | 描述 |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 上游 11 个 stage 证据审计 + 4/4 AMM reject 总结 + final LP research stage 标志 |
| `input_evidence_audit.json` | 审计结构化 (amm_cumulative_4_reject, is_final_lp_research_stage=true) |

## 阶段 C — stable AMM source audit

| file | 描述 |
|---|---|
| `STABLE_AMM_SOURCE_AUDIT_CN.md` | 4 stable AMM 候选官方 source 审计 (Meteora Stable Swap = ex-Saber; DAMM v2; Orca; Raydium AMM v4) |
| `stable_amm_source_audit.json` | source URLs, candidate program ids, decision (Meteora DAMM v2 has stable pool_type) |

## 阶段 D — stable AMM program on-chain verify

| file | 描述 |
|---|---|
| `STABLE_AMM_PROGRAM_VERIFY_CN.md` | 4 programs on-chain verified; **Meteora API mislabel 重要 caveat** (USDC-USDT candidates are Orca-owned) |
| `stable_amm_program_verify.json` | verify 结果 + excluded candidates (32D4z... actual owner = Orca) |

## 阶段 E — candidate source collection

| file | 描述 |
|---|---|
| `stable_pool_candidate_source_collection.py` | 收集脚本 (Orca official API + Meteora DAMM v2 API) |
| `stable_pool_candidate_source_collection.json` | 27 unique candidates (25 Orca + 2 Meteora DAMM v2) |
| `stable_pool_candidate_source_collection.csv` | CSV form |

## 阶段 F — chain verify + dedupe

| file | 描述 |
|---|---|
| `stable_pool_chain_verify.py` | getAccountInfo 验证 (4 accepted programs) |
| `stable_pool_chain_verification.json` | 25/27 verified (2 Meteora API candidates filtered as Orca-owned) |
| `stable_pool_chain_verification.csv` | CSV form |

## 阶段 G — pool decode

| file | 描述 |
|---|---|
| `stable_pool_decode_runner.js` | Node.js Orca SDK decode + Orca quote |
| `stable_pool_decode_snapshot.json` | 25 行 SDK decode 结果 (token_a, token_b, tick_spacing, fee_rate_bps, liquidity) |
| `stable_pool_decode_snapshot.csv` | 已在 runner 中 (CSV form) |

## 阶段 H — quote smoke

| file | 描述 |
|---|---|
| `stable_pool_decode_runner.js` (同 Stage G) | 同时跑 quote 10/20/100 USD via Orca SDK swapInstructions |
| `stable_pool_quote_smoke.json` | 75 行 (10 pools × 3 notionals + 部分 100u failures) |
| `stable_pool_quote_smoke.csv` | CSV form (in runner) |

## 阶段 I — survival EV preview

| file | 描述 |
|---|---|
| `stable_pool_survival_ev_preview.py` | EV preview (heuristic 0.5%/day turnover; LST-stable lower IL: 0.0005/0.002/0.008) |
| `stable_pool_survival_ev_preview.json` | 1680 行 (10 × 6 × 7 × 4) |
| `stable_pool_survival_ev_preview.csv` | CSV form |

## 阶段 J — candidate decision

| file | 描述 |
|---|---|
| `STABLE_POOL_DECISION_CN.md` | 7 项判断 + spec rule_2 + 5/5 AMM reject → STOP_LP_RESEARCH_NOW |
| `stable_pool_decision.json` | 决策结构化 (amm_cumulative_5_reject, recommended_next_stage=STOP_LP_RESEARCH_NOW) |

## 阶段 K — final verdict (LP research 收口)

| file | 描述 |
|---|---|
| `FINAL_VERDICT.json` | status=WARN, recommended_next_stage=STOP_LP_RESEARCH_NOW |
| `ONEPAGE_CN.md` | 一页总结 (LP research 收口 + 5/5 AMM reject 对比) |
| `ARTIFACT_INDEX.md` | 本文件 |

## data/ 子目录

- `data/collection_summary.json`
- `data/chain_verify_summary.json`
- `data/decode_quote_summary.json`
- `data/survival_ev_summary.json`

## 安全断言总览 (跨阶段)

| 阶段 | touched_trading_path | touched_wallet_tx_bridge_live_paper | keypair | signer | transaction |
|---|---|---|---|---|---|
| A–K | no | no | no | no | no |

## LP Research 累计 5 stages (全 reject)

| 阶段 | RUN_ID | best cell | positive_realistic |
|---|---|---|---|
| Meteora DLMM V8 | 20260604_021913 | +$0.544 | 0 |
| Orca Whirlpools V1 | 20260604_025414 | +$0.106 | 0 |
| Raydium CLMM V1 | 20260604_034503 | +$0.167 | 0 |
| Raydium CPMM V1 | 20260604_040952 | +$0.172 | 0 |
| **Orca stable (this)** | **20260604_044118** | **+$0.204** | **0** |
| **summary** | | all < $0.55 in zero_il_lvr | **5/5 reject** |
