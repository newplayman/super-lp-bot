# Input Evidence Audit — Stage B

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`
- branch: `feat/supabase-postgres-deployment`
- head_before: `b4327d4`

## 0. 阶段目标

实现 Raydium CPMM (constant product) read-only connector V1。
按 spec rule_2 + 累计 3/3 V3 CL AMM reject 结论 + user 上一轮 instruction "不再 V3 CL 无限扩展, 切到 Raydium CPMM / stable pool / non-CL LP"。
**只做**: CPMM program/SDK 审计、program 链上验证、SDK 隔离安装、候选池收集、链上 owner 验证、pool reserve/vault/fee decode、read-only quote (constant product 公式)、survival EV preview。
**不接钱包 / 不读 keypair / 不签名 / 不发交易 / 不 open/close LP / 不 add/remove liquidity / 不 collect fee / 不 swap**。

## 1. 上游证据链读取清单

| # | path | 角色 | 状态 |
|---|---|---|---|
| 1 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/FINAL_VERDICT.json` | **直接上游** — V1 CLMM 结束态 | OK |
| 2 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/ONEPAGE_CN.md` | CLMM V1 一句话总结 | OK |
| 3 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/RAYDIUM_CLMM_SURVIVAL_EV_PREVIEW_CN.md` | EV 8400 cells | OK |
| 4 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/raydium_clmm_survival_ev_preview.csv` | EV 网格 | OK |
| 5 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/RAYDIUM_CLMM_CANDIDATE_DECISION_CN.md` | CLMM V1 decision (rule_2 → CPMM) | OK |
| 6 | `reports/lp_raydium_clmm_readonly_connector/20260604_034503/raydium_clmm_candidate_decision.json` | 决策结构化 | OK |
| 7 | `reports/lp_solana_rpc_registry_fix/20260603_093136/FINAL_VERDICT.json` | V1 RPC registry (4/6 verified) | OK |
| 8 | `reports/lp_solana_rpc_registry_fix/20260603_093136/solana_program_id_registry_v2.json` | **CPMM pid 历史 fail 记录**: CPMMoo8... not on mainnet/devnet | OK |
| 9 | `reports/lp_solana_connector_design/20260603_080347/RAYDIUM_CONNECTOR_DESIGN_CN.md` | 早 V1 stage Raydium design | OK |
| 10 | `reports/lp_solana_connector_design/20260603_080347/raydium_connector_design.json` | 设计 schema | OK |

## 2. 关键事实确认

```text
previous Raydium CLMM V1 stage:
  candidate_raw_count         = 107
  verified_pool_count         = 65
  sdk_decode_success_count    = 65
  tick_array_ready_pool_count = 2
  quote_ready_pool_count      = 50
  row_count                   = 8400
  positive_zero_il_lvr_count  = 480
  positive_optimistic_count   = 0
  positive_realistic_count    = 0
  positive_conservative_count = 0
  near_break_even_count       = 1680
  best_net_ev_proxy_usd       = +0.167 (only in zero_il_lvr scenario, 2000/7d)
  recommended_next_stage      = LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1 (per user instruction)

V3 CL 累计 3/3 reject:
  Meteora DLMM V8     : best +0.544, 0 realistic
  Orca Whirlpools V1  : best +0.106, 0 realistic
  Raydium CLMM V1     : best +0.167, 0 realistic
```

## 3. 重要 Caveat (从上游)

**Raydium CPMM 历史上的 program id 验证失败 (V1 stage 20260603_093136)**:
- candidate `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` (来自 `raydium-cp-swap` 仓库 `declare_id!`)
- **NOT on mainnet** AND **NOT on devnet** (V1 stage 双重确认 fail)
- V1 devnet fallback `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` 也 null
- 推测原因: 该 pid 是 **legacy** 或 **next-gen** swap program, 不是 deployed program

**本轮必须**:
1. 重新从官方 source 查 Raydium CPMM **真实 mainnet** program
2. on-chain 验证 (account exists, executable, owner)
3. 不得复用未验证 pid
4. 找不到 verified pid → output blocker, recommended = `LP_RAYDIUM_CPMM_PROGRAM_ID_FIX_REPEAT` 或 `STOP_LP_RESEARCH_NOW`

## 4. 候选 mainnet CPMM 路径 (待 Stage C 验证)

1. **Raydium AMM v4 (CPMM-equivalent)**: program id `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
   - 这是 Raydium 早期 constant-product AMM, data_len 752 bytes
   - 大量 mainnet 池子
   - 与 V8 Meteora 误标 dexId="meteora" 的那些池可能就是 Raydium AMM v4
2. **Raydium CPMM (cp-swap)**: candidate `CPMMoo8L...` (历史 fail, 需重查)
3. **其他未知**: 在 Stage C 审计

## 5. 本轮范围 (vs V1 早 stage design)

| 维度 | V1 早 stage (20260603_080347) | 本轮 (20260604_040952) |
|---|---|---|
| 设计 | 是 | 已 reference |
| 实现 connector | 否 | 是 (read-only) |
| 跑 RPC | 否 | 是 (public RPC) |
| 接 wallet | 否 | 否 (严格禁止) |
| 准备资金 | 否 | 否 |

## 6. 硬边界继承

```text
can_run_probe_now               = false (locked)
tiny_canary_allowed             = no    (locked)
solana_wallet_or_keypair_touched = false (locked)
transaction_sent                = false (locked)
v2_line_count                   = 992 (unchanged)
send_hard_disable_still_active  = true
```

## 7. 不读不写不构造

- ❌ 不读 Solana 私钥 / seed phrase / keypair json / wallet adapter
- ❌ 不构造 transaction
- ❌ 不调用 sendTransaction / open LP / close LP / addLiquidity / removeLiquidity / collectFee / swap
- ❌ 不 bridge
- ❌ 不启动 live / canary / paper
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 表
- ❌ 不修改 EVM executor
- ❌ 不释放 hard-disable

## 8. 允许的操作

- WebFetch / curl 官方 Raydium docs / 官方 GitHub / 官方 SDK / 官方 API
- npm install 到 /tmp 隔离目录
- Solana public RPC read-only (getAccountInfo, getMultipleAccountsInfo)
- Raydium SDK read-only decode
- reserve/vault 读取
- Constant product quote math
- JSON / CSV / MD / tests

## 9. 决策约束 (spec rule_2)

如果本轮:
- `positive_realistic_count > 0` 或 strong near-break-even stable pool → `LP_RAYDIUM_CPMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1`
- `quote_ready_pool_count > 0` 但全负 → `LP_SOLANA_STABLE_POOL_RESEARCH_V1`
- `quote_ready_pool_count = 0` → `LP_RAYDIUM_CPMM_KNOWN_POOL_FEED_EXPANSION_REPEAT` 或 `STOP_LP_RESEARCH_NOW`
- 不建议无限 CPMM repeat

## 10. 下一阶段

进入 Stage C — Raydium CPMM 官方 program / SDK source audit。
