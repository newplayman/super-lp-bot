# Artifact Index — LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1

- run_id: `20260604_040952`
- branch: `feat/supabase-postgres-deployment`
- head_before: `b4327d4`

## 阶段 A — workspace safety

(无 artifact; 检查结果在 Stage B 中记录)

## 阶段 B — input evidence audit

| file | 描述 |
|---|---|
| `INPUT_EVIDENCE_AUDIT_CN.md` | 上游 10 个 stage 证据审计 + V3 CL 累计 3/3 reject 总结 + cpmm_pid_history_caveat |
| `input_evidence_audit.json` | 审计结构化 (v3_cl_amm_cumulative, cpmm_pid_history_caveat) |

## 阶段 C — Raydium CPMM source audit

| file | 描述 |
|---|---|
| `RAYDIUM_CPMM_SOURCE_AUDIT_CN.md` | 官方 source 审计 (GitHub + npm); 3 个 candidate pid: AMM v4 (mainnet), cp-swap source-declared mainnet (not on mainnet), cp-swap devnet |
| `raydium_cpmm_source_audit.json` | source URLs, candidate program ids, decision (use AMM v4) |

## 阶段 D — CPMM program on-chain verify

| file | 描述 |
|---|---|
| `RAYDIUM_CPMM_PROGRAM_VERIFY_CN.md` | on-chain 验证 AMM v4 program (executable, owner=BPFLoader, 36 bytes data); 测试 pool |
| `raydium_cpmm_program_verify.json` | verify 结果 + rejected candidates |

## 阶段 E — SDK install audit

| file | 描述 |
|---|---|
| `RAYDIUM_CPMM_SDK_PACKAGE_AUDIT_CN.md` | v2 SDK install; liquidityStateV4Layout decode verified on SOL/USDC pool; V1 SDK PoolInfoLayout NOT applicable caveat |
| `raydium_cpmm_sdk_package_audit.json` | install 状态, read_only decode proof |

## 阶段 F — candidate source collection

| file | 描述 |
|---|---|
| `raydium_cpmm_candidate_source_collection.py` | 收集脚本 (GeckoTerminal raydium + DexScreener) |
| `raydium_cpmm_candidate_source_collection.json` | 127 unique candidates |
| `raydium_cpmm_candidate_source_collection.csv` | CSV form |

## 阶段 G — chain verify + dedupe

| file | 描述 |
|---|---|
| `raydium_cpmm_pool_chain_verify.py` | getAccountInfo 验证脚本 |
| `raydium_cpmm_pool_chain_verification.json` | 81/120 verified (39 owner_mismatch filtered) |
| `raydium_cpmm_pool_chain_verification.csv` | CSV form |

## 阶段 H — pool account decode

| file | 描述 |
|---|---|
| `raydium_cpmm_pool_decode_runner.js` | Node.js SDK decode runner (liquidityStateV4Layout) + vault balance read |
| `raydium_cpmm_pool_snapshot.json` | 81 行 SDK decode 结果 (baseMint, quoteMint, vault, lpMint, fee, reserves) |
| `raydium_cpmm_pool_snapshot.csv` | CSV form |

## 阶段 I — quote smoke

| file | 描述 |
|---|---|
| `raydium_cpmm_quote_smoke.py` | Constant product quote math (x*y=k) |
| `raydium_cpmm_quote_smoke.json` | 292 行 (73 pools × 4 notionals) |
| `raydium_cpmm_quote_smoke.csv` | CSV form |

## 阶段 J — survival EV preview

| file | 描述 |
|---|---|
| `raydium_cpmm_survival_ev_preview.py` | EV preview (heuristic 0.5%/day turnover; 25bps default fee; $0.003 cost) |
| `raydium_cpmm_survival_ev_preview.json` | 12264 行 (73 × 6 × 7 × 4) |
| `raydium_cpmm_survival_ev_preview.csv` | CSV form |

## 阶段 K — candidate decision

| file | 描述 |
|---|---|
| `RAYDIUM_CPMM_CANDIDATE_DECISION_CN.md` | 7 项判断 + spec rule_2 → LP_SOLANA_STABLE_POOL_RESEARCH_V1 |
| `raydium_cpmm_candidate_decision.json` | 决策结构化 (amm_cumulative_4_reject: 4/4 reject) |

## 阶段 L — final verdict

| file | 描述 |
|---|---|
| `FINAL_VERDICT.json` | status=WARN, recommended_next_stage=LP_SOLANA_STABLE_POOL_RESEARCH_V1 |
| `ONEPAGE_CN.md` | 一页总结 (counts + finding + 4 AMM 对比) |
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
| A–L | no | no | no | no | no |
