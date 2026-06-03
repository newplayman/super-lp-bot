# Meteora Coverage Expand V7 — 总览

```text
stage                                       = LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V2
run_id                                      = 20260603_150331
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 0729ea8 (V6 commit)

coverage_plan
  ready                                     = true
  tiers_designed                            = [12, 15]
  max_coverage                              = 15 (per spec "不得超过 15 arrays; 不得无限扩展")
  priority_pool                             = SOL/USDC (bin_step=2, tight)
  sanity_pool                               = X/USDC (bin_step=100, wide)

pda_derivation
  ran                                       = true
  total                                     = 32 (SOL/USDC 12+15; X/USDC 5 sanity)
  success                                   = 32/32 (deterministic; no RPC)

single_account_read
  ran                                       = true
  attempted                                 = 27 (8+10 SOL/USDC; 4 X/USDC; 5 nulls)
  success                                   = 18 (8 SOL/USDC 12_arrays + 10 SOL/USDC 15_arrays; 0 X/USDC nulls)
  403_count                                 = 0
  410_count                                 = 0
  account_null_count                        = 9 (4 SOL/USDC 12_arrays + 5 SOL/USDC 15_arrays; 1 X/USDC)

bin_liquidity_decode
  total_bins_decoded                         = 1540 (SOL/USDC 1260; X/USDC 280)
  bins_with_liquidity                        = 231 (X/USDC only; SOL/USDC has 0 in all 1260 bins)
  pool_1_sol_usdc_bins_with_liq              = 0 / 1260 (HONEST BLOCKER)
  pool_2_x_usdc_bins_with_liq                = 231 / 280 (V6 stable)

quote_smoke
  ran                                       = true
  attempted                                 = 4 (SOL/USDC 12 + 15 arrays × 2 notionals)
  success                                   = 0
  sol_usdc_10u_quote_success                 = false (blocked at 12 AND 15)
  sol_usdc_20u_quote_success                 = false (blocked at 12 AND 15)
  x_usdc_quote_still_success                 = true (V6: 6/6 stable; not re-run this round)

combined_quote_readiness
  sol_usdc_quote_ready                       = false (0/4 quote at 12/15 arrays)
  x_usdc_quote_ready                         = true (V6 6/6 stable)
  bin_liquidity_ready                        = partial (pool 1: 0/1260; pool 2: 231/280)
  quote_ready                                = partial (pool 1 blocked; pool 2 ready)
  survival_ev_ready                          = partial (only pool 2)
  can_enter_full_survival_ev_preview         = false
  can_enter_partial_survival_ev_preview      = true (pool 2 only)
  paid_rpc_required                          = true (15 arrays = 21% range still 0 liquidez in pool 1)

next_stage_decision
  recommended                                = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 (partial, pool 2 only)
  default                                    = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
  alternative                                = LP_SOLANA_PAID_RPC_SETUP_REQUIRED (if 2-pool EV needed)

key_breakthrough_v7
  v6_to_v7_coverage                          = 9 → 15 (spec hard cap)
  v6_to_v7_single_account_read               = 33/42 → 18/27 SOL/USDC (0 RPC errors; scales)
  v6_to_v7_bins_with_liquidity_pool_1        = 0 → 0 (real on-chain: 0 liquidity in ±10% range)
  v6_to_v7_quote_attempted                   = 12 → 16 (pool 2 sanity not re-run; pool 1 added 4 attempts)
  v6_to_v7_quote_success                     = 6 → 6 (pool 2 unchanged; pool 1 still 0/8 across V5+V6+V7)
  v7_hits_spec_hard_cap_15                   = per spec STOP expansion; recommend partial EV or paid RPC

safety locks (all intact)
  can_run_probe_now                          = false
  execution_allowed_now                      = false
  transaction_sent                           = false
  wallet_or_tx_touched                       = false
  solana_wallet_or_keypair_touched           = false
  tiny_canary_allowed                        = "no"
  edge_proven                                = "no"
  hard_disable_still_active                  = true
  v2_line_count_unchanged                    = true (992)
```

## 一句话

V7 在 V6 基础上 **扩展 coverage 9 → 12/15 arrays** (per spec "max 15; 不得无限扩展" 硬规则; **V7 hit spec cap**): **(1) Stage D 32/32 PDA 推导** (deterministic, no RPC); **(2) Stage E 18/27 single-account getAccountInfo success** on public RPC (0 403, 0 410; 9 account_null = un-initialized bin arrays); **(3) Stage F 1540 bins decoded**; **(4) Stage G 0/4 SOL/USDC quote at 12+15 arrays**; **(5) 关键 finding: pool 1 (SOL/USDC bin_step=2) has 0 bins with liquidez at 12 (16.8% range) AND 15 (21% range)** = 0/1260 bins combined; 真实 on-chain 数据, **不是 RPC 限制**; V7 hit spec hard cap, **STOP expansion**; next stage = `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` (partial, pool 2 only) or `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`. 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; repo `node_modules/` **未**创建.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=0729ea8; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (10 upstream files from V6) |
| C 12/15 coverage plan | PASS (12/15 tiers; max 15 hard rule; auto-checkpoint at 12) |
| D PDA derivation 12/15 | PASS (32/32 deterministic pubkeys; SOL/USDC 12+15; X/USDC 5) |
| E single-account read 12/15 | PASS (18/27 success; 0 RPC errors; 9 account_null) |
| F bin liquidity decode 12/15 | PASS (1540 bins; pool 1: 0/1260 with liquidez; pool 2: 231/280) |
| G SOL/USDC quote v4 | BLOCKED (0/4; 15 arrays = spec cap) |
| H combined quote readiness v2 | PASS (6 tables: 3 ready / 3 partial) |
| I next-stage decision | PASS (LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1 selected) |
| J FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| K tests + safety scan | pending |
| L git publish | pending |

## 严格禁区（本轮已遵守, 19/19）

```text
× 未读 Solana 私钥 / seed phrase / keypair / wallet adapter
× 未创建 signer
× 未构造 transaction
× 未调用 sendTransaction
× 未调用 swap (tx builder) / open_lp / close_lp / collect_fee
× 未启动 live / canary / paper
× 未桥接 / 自动换币
× 未写 production positions / shadow 表
× 未修改 EVM executor v2 源码 (line count 992 不变)
× send hard-disable 仍存在（未解除）
× 未 hard-code 任何 protocol program id (除文档/源码 引用)
× 未 webfetch blog / Twitter / 论坛 / unofficial GitHub
× 未 paid RPC call (无 key)
× 未在 repo root 安装任何 npm package (只在 /tmp/lpbot_meteora_dlmm_sdk_probe_20260603_130532/)
× 未 instantiate Keypair
× 未 import @solana/wallet-adapter-*
× 未调用 position-create / addLiquidity / removeLiquidity / closePosition / claimFee / claimReward
× swapQuote 调 read-only 函数 (returns quote object); **不**构造 transaction
× repo node_modules/ 未创建
```

## 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1` (partial, pool 2 only)
- 关键 input 需求:
  1. (默认) **接受 partial EV preview** (pool 2 only; X/USDC only; mark pool 1 as no_quote_data)
  2. (若 operator 想要 2-pool EV) **提供 paid RPC key** (Helius / Triton / QuickNode); 选 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED`
  3. (可选) **扩展 known pool feed** (找更易 quote 的 Meteora DLMM 池; 但仍 public RPC)
- 不建议再 fix_repeat (V7 hit spec cap)
- 不建议 STOP (read-only path fully working; partial EV possible; pool 1 真实 liquidity 缺失)
- 即便选 survival EV preview, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
