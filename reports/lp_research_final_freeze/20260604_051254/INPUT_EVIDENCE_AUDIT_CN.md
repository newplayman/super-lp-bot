# Input Evidence Audit — Stage B

- stage: `LP_RESEARCH_FINAL_FREEZE_AND_HANDOFF_V1`
- run_id: `20260604_051254`
- branch: `feat/supabase-postgres-deployment`
- head_before: `b3cdf23`

## 0. 阶段目标

做 LP research 当前主线最终冻结、归档、交接文档。本轮是 LP research 主线的**收口阶段**, 选 `STOP_LP_RESEARCH_NOW`。
- 不启动新 research runner
- 不继续换协议
- 不 probe / canary / live / paper
- 不读 keypair / 构造 tx

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | 4/4 reject evidence 1 | OK |
| 2 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json` | 4/4 reject evidence 2 | OK |
| 3 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json` | 4/4 reject evidence 3 | OK |
| 4 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json` | 4/4 reject evidence 4 | OK |
| 5 | `reports/lp_solana_stable_pool_research/20260604_044118/FINAL_VERDICT.json` | 5/5 reject evidence 5 + STOP | OK |
| 6 | `docs/LPBOT_RESEARCH_STATUS_CN.md` | project status doc | OK |
| 7 | `docs/LPBOT_RESEARCH_ARTIFACT_INDEX_CN.md` | artifact index doc | OK |
| 8 | `README.md` | top-level readme | OK |

## 2. 关键事实确认 (5/5 AMM reject + STOP)

```text
=== LP research 累计 5 stages (5/5 reject) ===

1. Meteora DLMM V8           (20260604_021913)
   candidate_raw_count = 60,  verified = 56,  quote-ready = 27
   best cell +$0.544 (zero_il_lvr), positive_realistic = 0
   recommended_next_stage = LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1

2. Orca Whirlpools V1        (20260604_025414)
   candidate_raw_count = 15002, verified = 75,  quote-ready = 10
   best cell +$0.106 (zero_il_lvr), positive_realistic = 0
   recommended_next_stage = LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1

3. Raydium CLMM V1          (20260604_034503)
   candidate_raw_count = 107,  verified = 65,  quote-ready = 50
   best cell +$0.167 (zero_il_lvr), positive_realistic = 0
   recommended_next_stage = LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1

4. Raydium CPMM V1 (AMM v4) (20260604_040952)
   candidate_raw_count = 127,  verified = 81,  quote-ready = 73
   best cell +$0.172 (zero_il_lvr), positive_realistic = 0
   recommended_next_stage = LP_SOLANA_STABLE_POOL_RESEARCH_V1

5. Solana Stable Pool V1    (20260604_044118)
   candidate_raw_count = 27,   verified = 25,  quote-ready = 10
   best cell +$0.204 (zero_il_lvr), positive_realistic = 0
   recommended_next_stage = STOP_LP_RESEARCH_NOW (this stage final)

all 5:  can_run_probe_now = false  ✓
all 5:  tiny_canary_allowed = no  ✓
all 5:  solana_wallet_or_keypair_touched = false  ✓
all 5:  transaction_sent = false  ✓
all 5:  best cell < $0.55,  only positive in zero_il_lvr scenario
```

## 3. 累计结论 (per spec rule_2 + 5/5 reject)

- **positive_realistic = 0** across all 5 protocols
- **positive_optimistic = 0**
- **positive_conservative = 0**
- **positive_zero_il_lvr only** (heuristic, not real)
- **all best cells under $0.55** at 7d 2000 USD notional
- **5/5 Solana AMM protocols reject** retail 10-20U 2000 USD LP

## 4. 本轮范围 (LP research 收口)

| 维度 | 状态 |
|---|---|
| 启动新 research runner | ❌ 禁止 |
| 换协议 | ❌ 禁止 |
| probe / canary / live / paper | ❌ 禁止 |
| 读 keypair / 构造 tx | ❌ 禁止 |
| 汇总报告 | ✅ 允许 |
| 更新 docs | ✅ 允许 |
| 更新 artifact index | ✅ 允许 |
| 最终冻结矩阵 | ✅ 允许 |
| 重开条件 | ✅ 允许 |
| future research backlog | ✅ 允许 |
| 安全检查 | ✅ 允许 |
| commit / push | ✅ 允许 |

## 5. 硬边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
wallet_or_tx_touched            = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 6. 下一阶段

进入 Stage C — 构建 LP_RESEARCH_FINAL_FREEZE_MATRIX (7 protocols 累计矩阵)。
