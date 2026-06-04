# Artifact Index — LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1

- run_id: `20260604_021913`
- branch: `feat/supabase-postgres-deployment`
- head_before: `852c976`

## 阶段 A — workspace safety

(无 artifact; 检查结果在 Stage B 中记录)

## 阶段 B — input evidence audit

| file | 描述 |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 上游 9 个 stage 证据审计 |
| `input_evidence_audit.json` | 审计结构化 (previous_stage_facts_confirmed, safety_locks) |

## 阶段 C — targeted pool source strategy

| file | 描述 |
|---|---|
| `METEORA_TARGETED_POOL_SOURCE_STRATEGY_CN.md` | 5-dim 目标 (high_fee / high_volume / high_liquidity / quote_friendly / token_quality) + source priority |
| `meteora_targeted_pool_source_strategy.json` | 5-dim threshold / 候选源优先级 / 失败模式决策 |

## 阶段 D — targeted candidate source collection

| file | 描述 |
|---|---|
| `meteora_targeted_candidate_source_collection.py` | 收集脚本 (GeckoTerminal + DexScreener) |
| `meteora_targeted_candidate_source_collection.json` | 60 个 candidate 池 (53 GT + 7 DS) |
| `meteora_targeted_candidate_source_collection.csv` | CSV form (pool_address, name, vol24h, source_type) |
| `METEORA_TARGETED_CANDIDATE_SOURCE_COLLECTION_CN.md` | 60 池来源策略报告 + 公开 API 状态 |

## 阶段 E — chain verify + dedupe

| file | 描述 |
|---|---|
| `meteora_targeted_pool_chain_verify.py` | getAccountInfo 验证脚本 (并行 8 worker) |
| `meteora_targeted_pool_chain_verify.json` | 60 行 verify 结果 (56 verified, 4 mislabeled filtered) |
| `meteora_targeted_pool_chain_verify.csv` | CSV form |
| `METEORA_TARGETED_POOL_CHAIN_VERIFY_CN.md` | 链上验证报告 + 4 个被过滤池 (2 Raydium + 2 Orca Whirlpool) |

## 阶段 F — SDK decode targeted batch

| file | 描述 |
|---|---|
| `meteora_targeted_pool_decode_runner.js` | Node.js SDK decode runner (@meteora-ag/dlmm v1.9.10) |
| `meteora_targeted_pool_snapshot.json` | 56 行 SDK decode 结果 (token_x/y, bin_step, base/max fee bps) |
| `meteora_targeted_pool_snapshot.csv` | CSV form |
| `METEORA_TARGETED_POOL_SNAPSHOT_CN.md` | 56 池 fee 分布 + bin_step 分布 + 结构性 finding (max_fee=10% for all, base_fee 0.01%–1%) |

## 阶段 G — bin liquidity / quote targeted smoke

| file | 描述 |
|---|---|
| `meteora_targeted_quote_runner.js` | Node.js quote runner (single-account getMultipleAccountsInfo + DLMM.decodeAccount + pool.swapQuote) |
| `meteora_targeted_quote_readiness.json` | 27 行 quote 结果 (outAmount, fee, price_impact) |
| `meteora_targeted_quote_readiness.csv` | CSV form |
| `METEORA_TARGETED_QUOTE_READINESS_CN.md` | 27/27 quote 成功 (vs 上一轮 0); path 走通, V7 阻断被打破 |

## 阶段 H — survival EV preview

| file | 描述 |
|---|---|
| `meteora_targeted_survival_ev.py` | EV preview script (heuristic turnover) |
| `meteora_targeted_survival_ev.json` | 4536 行 EV 网格 (27 pool × 6 × 7 × 4) |
| `meteora_targeted_survival_ev.csv` | CSV form |
| `METEORA_TARGETED_SURVIVAL_EV_CN.md` | 15 positive cells 全在 zero_il_lvr/7d/>=500 USD; best +$0.544 |

## 阶段 I — candidate decision

| file | 描述 |
|---|---|
| `METEORA_TARGETED_CANDIDATE_DECISION_CN.md` | 7 项判断 + spec rule_2 应用 → Orca Whirlpools |
| `meteora_targeted_candidate_decision.json` | 决策结构化 (reasons[], rejected_alternatives) |

## 阶段 J — final verdict

| file | 描述 |
|---|---|
| `FINAL_VERDICT.json` | status=WARN, recommended_next_stage=LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1 |
| `ONEPAGE_CN.md` | 一页总结 (counts + 关键 finding + 决定 + 不做什么) |
| `ARTIFACT_INDEX.md` | 本文件 |

## data/ 子目录

- `data/collection_summary.json`
- `data/chain_verify_summary.json`
- `data/decode_summary.json`
- `data/quote_summary.json`
- `data/survival_ev_summary.json`

## 安全断言总览 (跨阶段)

| 阶段 | touched_trading_path | touched_wallet_tx_bridge_live_paper | keypair | signer | transaction |
|---|---|---|---|---|---|
| A–J | no | no | no | no | no |
