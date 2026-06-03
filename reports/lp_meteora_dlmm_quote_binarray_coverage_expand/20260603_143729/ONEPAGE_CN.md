# Meteora Coverage Expand V6 — 总览

```text
stage                                       = LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1
run_id                                      = 20260603_143729
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 202de5b (V5 commit)

coverage_plan
  ready                                     = true
  tiers_designed                            = [3, 5, 7, 9]
  max_coverage                              = 9 (per spec "不得无限扩展")
  next_tier_suggestion                      = 12-15 (slightly beyond spec; bounded)

expanded_pda_derivation
  ran                                       = true
  total                                     = 42 (2 pools × 3 tiers × 5-9 offsets)
  success                                   = 42/42 (deterministic; no RPC)

expanded_single_account_read
  ran                                       = true
  attempted                                 = 42
  success                                   = 33 (single-account OK on public RPC)
  failed                                    = 9 (account_null = un-initialized bin array accounts)
  403_count                                 = 0
  410_count                                 = 0

expanded_bin_liquidity_decode
  total_bins_decoded                         = 2310
  bins_with_liquidity                        = 731
  by_coverage_5                             = 630 / 231
  by_coverage_7                             = 770 / 301
  by_coverage_9                             = 910 / 371

quote_smoke_v3
  ran                                       = true
  attempted                                 = 12 (3 tiers × 2 pools × 2 notionals)
  success                                   = 6 (50%)
  pool_1_sol_usdc                           = 0/6 (BLOCKED on Insufficient liquidity at all tiers)
  pool_2_x_usdc                             = 6/6 (STABLE; 10U=941005; 20U=1882010)
  real_quote_data                           = 1 X ≈ 10.62 USDC (1/0.0941)

quote_readiness_update
  pool_snapshot_ready                       = yes
  fee_snapshot_ready                        = yes
  bin_liquidity_ready                       = partial (pool 1 needs >9 arrays)
  quote_ready                               = partial (pool 1 blocked; pool 2 ready)
  survival_ev_ready                         = partial (only pool 2 quote data)

paid_rpc_decision
  paid_rpc_required                          = partial (NOT true)
  single_account_path_works                  = yes (V5+V6: 39/48 reads success on public RPC)
  alternative_to_paid_rpc                    = 12-15 arrays on public RPC OR skip pool 1

next_stage_decision
  recommended                                = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
  default                                    = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
  next_tier                                  = 12-15 arrays (slightly beyond spec's 9 max)

key_breakthrough_v6
  V5_to_V6_single_account_read              = 6 → 33 (5.5x)
  V5_to_V6_bins_decoded                      = 420 → 2310 (5.5x)
  V5_to_V6_quote_attempted                   = 4 → 12 (3x)
  V5_to_V6_quote_success                     = 2 → 6 (3x for pool 2; pool 1 stable 0)
  pool_1_blocked_at_every_tier               = honest finding; not RPC issue; liquidity too far

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

V6 在 V5 基础上 **扩展 coverage 3 → 5/7/9 arrays** (per tier, 严格 "不得无限扩展" 边界): **(1) Stage D 42/42 PDA 推导** (deterministic, no RPC); **(2) Stage E 33/42 single-account getAccountInfo success** on public RPC (0 403, 0 410; 9 失败 = account_null = un-initialized bin array accounts); **(3) Stage F 2310 bins decoded** (5_arrays: 630; 7_arrays: 770; 9_arrays: 910; 731 with liquidity); **(4) Stage G 6/12 quote success**: **pool 2 (X/USDC) 6/6 STABLE** (10U → 941005 raw X; 20U → 1882010 raw X; 1 X ≈ 10.62 USDC); **pool 1 (SOL/USDC) 0/6 STILL blocked** even with 9 arrays × 70 bins = 630 bins ≈ 12% price range; 池 1 liquidity 离 active bin 太远, **不是 RPC 限制**; 下一阶段 fix_repeat 试 12-15 arrays (slightly beyond spec). **paid_rpc_required = partial** (NOT true); single-account path on public RPC 足够几乎所有场景, 池 1 需更宽 coverage OR paid RPC GPA. 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; repo `node_modules/` **未**创建.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=202de5b; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (10 upstream files from V5) |
| C coverage plan | PASS (3/5/7/9 arrays plan with cost + risk estimates) |
| D expanded PDA derivation | PASS (42/42 deterministic pubkeys; no RPC) |
| E expanded single-account read | PASS (33/42 success; 0 RPC errors; 9 account_null = un-initialized) |
| F expanded bin liquidity decode | PASS (2310 bins decoded; 731 with liquidity) |
| G quote smoke v3 | PARTIAL (6/12; pool 2 6/6 stable; pool 1 0/6 still blocked) |
| H quote readiness update | PASS (6 tables judged: 3 ready / 3 partial) |
| I next-stage decision | PASS (LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT selected) |
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

- 默认下一阶段 = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求（建议下个 prompt 提供）:
  1. (默认) **同意扩 coverage 9 → 12-15 arrays** (next fix_repeat 第一步, 仍 public RPC)
  2. (若 12-15 仍 blocked) **paid RPC 决策** (Phase 2B)
  3. (可选) **skip pool 1 EV**, 用 only pool 2 (immediate partial EV)
  4. (可选) **swapQuote maxExtraBinArrays=10** (let SDK try harder)
- 不建议直接进 EV preview (6/12 quote; partial EV; not full evaluation)
- 不建议 STOP (33/42 single-account + 2310 bins + 6/12 quote = 显著进步)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
