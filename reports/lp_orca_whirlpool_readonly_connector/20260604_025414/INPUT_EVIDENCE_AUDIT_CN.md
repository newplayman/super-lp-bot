# Input Evidence Audit — Stage B

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`
- branch: `feat/supabase-postgres-deployment`
- head_before: `22d2941`

## 0. 阶段目标

实现 Orca Whirlpools 的 read-only connector V1。只做池发现、链上校验、Whirlpool account decode、tick array read、quote smoke、survival EV preview 的前置数据。
**不接钱包 / 不读 keypair / 不签名 / 不发交易 / 不 open/close LP / 不 collect fee / 不 swap**。

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json` | **直接上游** — 上一轮 targeted 结束态 | OK |
| 2 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/ONEPAGE_CN.md` | 上一轮一句话总结 | OK |
| 3 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/METEORA_TARGETED_SURVIVAL_EV_CN.md` | EV 1536 cells (27 pool × 6×7×4) | OK |
| 4 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/meteora_targeted_survival_ev.csv` | EV 网格原始数据 | OK |
| 5 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/METEORA_TARGETED_CANDIDATE_DECISION_CN.md` | 上一轮 decision (rule_2 → Orca) | OK |
| 6 | `reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/meteora_targeted_candidate_decision.json` | 决策结构化 | OK |
| 7 | `reports/lp_solana_rpc_registry_fix/20260603_093136/FINAL_VERDICT.json` | V1 RPC registry fix (4/6 verified) | OK |
| 8 | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` | Orca program id `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | OK |
| 9 | `reports/lp_solana_connector_design/20260603_080347/ORCA_WHIRLPOOL_CONNECTOR_DESIGN_CN.md` | 早 V1 阶段 Orca connector 设计 | OK |
| 10 | `reports/lp_solana_connector_design/20260603_080347/orca_whirlpool_connector_design.json` | 设计 schema | OK |

## 2. 关键事实确认

```text
previous Meteora targeted stage:
  candidate_raw_count         = 60
  verified_pool_count         = 56
  sdk_decode_success_count    = 56
  quote_ready_pool_count      = 27
  row_count                   = 4536
  positive_realistic_count    = 0
  positive_optimistic_count   = 0
  positive_conservative_count = 0
  positive_zero_il_lvr_count  = 15
  near_break_even_count       = 19
  best_net_ev_proxy_usd       = +0.544
  recommended_next_stage      = LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1 (rule_2)

Orca Whirlpool program id:
  program_id    = whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc
  source        = https://github.com/orca-so/whirlpools (official_github)
  source_confidence = high
  on-chain verified in V1 (20260603_093136)

V1 早 V1 阶段 design (20260603_080347) 已知:
  - SDK: @orca-so/whirlpools-sdk
  - Whirlpool account size ~ 800 bytes
  - TickArray size = 88
  - TickArray PDA: derive_tick_array_pda(whirlpool_pubkey, start_tick_index)
  - Position NFT model
  - Quote: swap_quote (TypeScript helper) OR simulateTransaction
  - Round-trip cost: $0.005-0.008
```

## 3. 本轮范围 (V1 早 stage 范围 vs 本轮 V1 stage)

| 维度 | V1 早 stage (20260603_080347) | 本轮 (20260604_025414) |
|---|---|---|
| 设计 | 是 | 已 reference |
| 实现 connector | 否 | 是 (read-only) |
| 跑 RPC | 否 | 是 (public RPC) |
| 接 wallet | 否 | 否 (严格禁止) |
| 准备资金 | 否 | 否 |

## 4. 硬边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 5. 不读不写不构造

- ❌ 不读 Solana 私钥 / seed phrase / keypair json / wallet adapter
- ❌ 不构造 transaction
- ❌ 不调用 sendTransaction / open_position / close_position / increaseLiquidity / decreaseLiquidity / collectFees / swap
- ❌ 不 bridge
- ❌ 不启动 live / canary / paper
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 表
- ❌ 不修改 EVM executor
- ❌ 不释放 hard-disable

## 6. 允许的操作

- WebFetch / curl 官方 Orca docs / 官方 GitHub / 官方 SDK
- npm install 到 /tmp 隔离目录
- Solana public RPC read-only (getAccountInfo, getMultipleAccountsInfo)
- Orca SDK account decode (read-only)
- Whirlpool account decode
- Tick array PDA derive
- Tick array account read/decode
- Read-only quote / quote object
- JSON / CSV / MD / tests

## 7. 决策约束 (spec rule_2)

如果本轮:
- `positive_realistic_count > 0` → `LP_ORCA_WHIRLPOOL_10_20U_PROBE_PREFLIGHT_DESIGN_V1`
- `quote_ready_pool_count > 0` 但全负 → `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- `quote_ready_pool_count = 0` → `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1` 或 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`

## 8. 下一阶段

进入 Stage C — Orca 官方 SDK / program source audit (audit 官方 GitHub repo / official SDK / examples)。
