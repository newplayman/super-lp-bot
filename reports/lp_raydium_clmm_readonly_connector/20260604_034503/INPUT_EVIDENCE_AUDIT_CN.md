# Input Evidence Audit — Stage B

- stage: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_034503`
- branch: `feat/supabase-postgres-deployment`
- head_before: `9f0495a`

## 0. 阶段目标

实现 Raydium CLMM 的 read-only connector V1。这是 **3rd V3 类 CL AMM 独立验证** (前两个: Meteora DLMM V8 + Orca Whirlpools V1 都 reject)。
只做池发现、链上校验、PoolState decode、tick array read、quote smoke、survival EV preview 的前置数据。
**不接钱包 / 不读 keypair / 不签名 / 不发交易 / 不 open/close LP / 不 collect fee / 不 swap**。

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/FINAL_VERDICT.json` | **直接上游** — V1 Orca 结束态 | OK |
| 2 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/ONEPAGE_CN.md` | Orca V1 一句话总结 | OK |
| 3 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/ORCA_SURVIVAL_EV_PREVIEW_CN.md` | Orca EV 1680 cells | OK |
| 4 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/orca_survival_ev_preview.csv` | EV 网格原始数据 | OK |
| 5 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/ORCA_CANDIDATE_DECISION_CN.md` | Orca decision (rule_2 → Raydium) | OK |
| 6 | `reports/lp_orca_whirlpool_readonly_connector/20260604_025414/orca_candidate_decision.json` | 决策结构化 | OK |
| 7 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | V8 Meteora 结束态 | OK |
| 8 | `reports/lp_solana_rpc_registry_fix/20260603_093136/FINAL_VERDICT.json` | V1 RPC registry (4/6 verified) | OK |
| 9 | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` | Raydium CLMM program id verified | OK |
| 10 | `reports/lp_solana_connector_design/20260603_080347/RAYDIUM_CONNECTOR_DESIGN_CN.md` | 早 V1 stage Raydium design | OK |

## 2. 关键事实确认

```text
previous Orca V1 stage:
  candidate_raw_count         = 15002
  verified_pool_count         = 75
  sdk_decode_success_count    = 75
  tick_array_ready_pool_count = 4
  quote_ready_pool_count      = 10
  row_count                   = 1680
  positive_realistic_count    = 0
  positive_optimistic_count   = 0
  positive_conservative_count = 0
  positive_zero_il_lvr_count  = 29
  near_break_even_count       = 928
  best_net_ev_proxy_usd       = +0.106
  recommended_next_stage      = LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1 (rule_2)

Meteora V8 stage (累计 2/3 reject):
  best_net_ev_proxy_usd       = +0.544 (only in zero_il_lvr scenario, 2000/7d)
  positive_realistic_count    = 0

Raydium CLMM program id:
  program_id    = CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK
  source        = https://github.com/raydium-io/raydium-clmm (official_github)
  source_confidence = high
  on-chain verified in V1 (20260603_093136)
  secondary_program_id_devnet = DRayAUgENGQBKVaX8owNhgzkEDyoHTGVEGHVJT1E9pfH
```

## 3. V3 CL AMM 累计结论 (本轮前置)

| 维度 | Meteora V8 (DLMM) | Orca V1 (Whirlpools) | Raydium (本轮) |
|---|---|---|---|
| 协议类型 | DLMM (dynamic fee, IL binary) | V3 CL (gradual IL) | V3 CL (gradual IL) |
| 候选源 | GeckoTerminal + DexScreener | Orca official API (14983) | TBD |
| Verify rate | 56/60 (93%) | 75/75 (100%) | TBD |
| Quote-ready | 27/56 (48%) | 10/75 (受 429, 实际 ~30+) | TBD |
| Best cell | +$0.544 | +$0.106 | TBD |
| positive_realistic | 0 | 0 | **TBD (key decision)** |
| positive_zero_il_lvr | 15 | 29 | TBD |
| Fee 范围 | 0.01%–1% | 0.01%–2% | TBD |

**3rd V3 CL AMM 独立验证, 完成 V3 CL 累计 reject 3/3 验证逻辑**:
- 3/3 V3 CL reject → 强结论 "零售 LP 在 Solana 10-20U 2000 USD 不可行"
- 任一 V3 CL positive → 重新评估, 进入 10/20U probe preflight design

## 4. 本轮范围 (vs V1 早 stage design)

| 维度 | V1 早 stage (20260603_080347) | 本轮 (20260604_034503) |
|---|---|---|
| 设计 | 是 | 已 reference |
| 实现 connector | 否 | 是 (read-only) |
| 跑 RPC | 否 | 是 (public RPC) |
| 接 wallet | 否 | 否 (严格禁止) |
| 准备资金 | 否 | 否 |

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
- ❌ 不调用 sendTransaction / openPosition / closePosition / increaseLiquidity / decreaseLiquidity / collectFees / collectReward / swap
- ❌ 不 bridge
- ❌ 不启动 live / canary / paper
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 表
- ❌ 不修改 EVM executor
- ❌ 不释放 hard-disable

## 7. 允许的操作

- WebFetch / curl 官方 Raydium docs / 官方 GitHub / 官方 SDK
- npm install 到 /tmp 隔离目录
- Solana public RPC read-only (getAccountInfo, getMultipleAccountsInfo)
- Raydium SDK account decode (read-only)
- PoolState account decode
- Tick array PDA derive
- Tick array account read/decode
- Read-only quote / quote object
- JSON / CSV / MD / tests

## 8. 决策约束 (spec rule_2 强化)

如果本轮:
- `positive_realistic_count > 0` → `LP_RAYDIUM_CLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1`
- `quote_ready_pool_count > 0` 但全负 → 切到 **Raydium CPMM** 或 **stable pool** 或 **non-CL LP** (per user instruction: 不要再无限 V3 CL 扩展)
- `quote_ready_pool_count = 0` → `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1` 或 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`

## 9. 下一阶段

进入 Stage C — Raydium CLMM 官方 SDK / program source audit。
