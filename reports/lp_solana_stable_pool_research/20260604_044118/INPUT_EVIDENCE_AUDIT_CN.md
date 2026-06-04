# Input Evidence Audit — Stage B

- stage: `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- run_id: `20260604_044118`
- branch: `feat/supabase-postgres-deployment`
- head_before: `8b2562a`

## 0. 阶段目标 (LP research 关键收口阶段)

审计 Solana stable-stable / low-IL LP 机会, 覆盖:
- Saber (历史 stable AMM)
- Mercurial Finance
- Meteora DAMM v2 stable pools
- Orca Whirlpool stable-like (USDC/USDT 0.01% fee)
- Raydium stable-like
- Lifinity

寻找 active stable-stable / SOL-LST / LST-LST / stable-LST 池, 跑 read-only quote + survival EV, **判断是否存在 10/20U realistic positive 或 strong near-break-even 候选**。

**如果仍然没有 → 正式 STOP_LP_RESEARCH_NOW** (此前 4/4 AMM 累计 reject 已强结论; stable pool 是最后 IL class).

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/FINAL_VERDICT.json` | **直接上游** — V1 CPMM 结束态 | OK |
| 2 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/ONEPAGE_CN.md` | CPMM V1 一句话总结 | OK |
| 3 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/RAYDIUM_CPMM_SURVIVAL_EV_PREVIEW_CN.md` | EV 12264 cells | OK |
| 4 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/raydium_cpmm_survival_ev_preview.csv` | EV 网格 | OK |
| 5 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/RAYDIUM_CPMM_CANDIDATE_DECISION_CN.md` | CPMM V1 decision (rule_2 → stable pool) | OK |
| 6 | `reports/lp_raydium_cpmm_readonly_connector/20260604_040952/raydium_cpmm_candidate_decision.json` | 决策结构化 | OK |
| 7 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json` | V1 CLMM 结束态 | OK |
| 8 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json` | V1 Orca 结束态 | OK |
| 9 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | V8 Meteora 结束态 | OK |
| 10 | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` | V1 RPC registry; **Lifinity pid unknown** | OK |
| 11 | `reports/lp_solana_connector_design/20260603_080347/RAYDIUM_CONNECTOR_DESIGN_CN.md` | 早 V1 stage Raydium design | OK |

## 2. 累计 4 AMM reject 总结 (V1 阶段历史)

| 协议 | 类型 | best cell | positive_realistic | 备注 |
|---|---|---|---|---|
| Meteora DLMM V8 | DLMM (V3) | +$0.544 | 0 | dynamic fee, IL binary |
| Orca Whirlpools V1 | V3 CL | +$0.106 | 0 | 16bps fee, lazy tick array |
| Raydium CLMM V1 | V3 CL | +$0.167 | 0 | 25bps fee, lazy tick array |
| **Raydium CPMM V1 (AMM v4)** | **constant product** | **+$0.172** | **0** | 25bps fee, 100% IL on price change |

**4/4 Solana AMMs 全部 reject retail 10-20U 2000 USD LP** in zero_il_lvr only.

## 3. 本轮范围 (LP research 关键收口)

这是 LP research 的最后阶段:
- 如果 stable pool 找到 positive → 进入 probe preflight design
- 如果没有 → **正式 STOP_LP_RESEARCH_NOW** (V1 阶段 4/4 reject + 任何 stable pool 也 reject = 强结论 "零售 LP 在 Solana 不可行")

## 4. 候选 stable AMM (待 Stage C 审计)

| 协议 | 状态 | program id | 来源 |
|---|---|---|---|
| Saber | mostly deprecated | (需查证) | saber-hq/saber-core |
| Mercurial Finance | outdated | (需查证) | mercurial-finance/mercurial |
| Meteora DAMM v2 stable | active | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` (V1 verified) | meteora-ag/damm-v2-sdk |
| Orca Whirlpool stable (USDC/USDT) | active | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` (V1 verified) | orca-so/whirlpools |
| Raydium stable | V1 only 24 USDC-anchor pools | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` (V1 verified) | raydium-io/raydium-amm |
| Lifinity | unknown pid | unknown | (V1 stage 20260603_093136 confirmed pid not on mainnet) |

## 5. 硬边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 6. 不读不写不构造

- ❌ 不读 Solana 私钥 / seed phrase / keypair json / wallet adapter
- ❌ 不构造 transaction
- ❌ 不调用 sendTransaction / open LP / close LP / addLiquidity / removeLiquidity / collectFee / swap
- ❌ 不 bridge
- ❌ 不启动 live / canary / paper
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 表
- ❌ 不修改 EVM executor
- ❌ 不释放 hard-disable

## 7. 允许的操作

- WebFetch / curl 官方 Saber / Mercurial / Meteora / Orca / Raydium / Lifinity docs / GitHub / SDK
- npm install 到 /tmp 隔离目录
- Solana public RPC read-only (getAccountInfo, getMultipleAccountsInfo)
- 各种 protocol SDK read-only decode
- 读 reserve / vault / fee / LP supply
- Constant product / StableSwap quote math
- JSON / CSV / MD / tests

## 8. 决策约束 (LP research 收口)

- `positive_realistic_count > 0` 或 strong near-break-even stable pool → `LP_STABLE_POOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1`
- `quote_ready_pool_count > 0` 但全负 → `STOP_LP_RESEARCH_NOW` (这是关键的收口)
- `quote_ready_pool_count = 0` → `STOP_LP_RESEARCH_NOW`
- 不建议无限 stable repeat

## 9. 下一阶段

进入 Stage C — 审计各 stable AMM 官方 source + 候选 program id 收集。
