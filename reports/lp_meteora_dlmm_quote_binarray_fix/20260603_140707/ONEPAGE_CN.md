# Meteora Quote Bin Array Fix V5 — 总览

```text
stage                                       = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1
run_id                                      = 20260603_140707
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 1c3d8ea (V4 commit)

binarray_helper_audit
  ran                                       = true
  helpers_audited                           = 12
  helpers_usable_for_single_account_path    = 8
  single_account_path_identified            = yes

binarray_pda_derivation
  ran                                       = true
  total                                     = 6 (2 pools × 3 offsets)
  success                                   = 6
  method                                    = binIdToBinArrayIndex + deriveBinArray (no RPC; pure math + PDA)

single_account_smoke
  ran                                       = true
  attempted                                 = 6
  success                                   = 6 (PUBLIC RPC OK)
  403_count                                 = 0
  410_count                                 = 0
  data_len_per_bin_array                    = 10136 bytes

small_batch_smoke
  ran                                       = false (Stage E had full success)

bin_liquidity_decode
  total_rows                                = 420 (6 bin arrays × 70 bins)
  decode_success_count                      = 420

quote_smoke_v2
  ran                                       = true
  attempted                                 = 4 (2 pools × 2 notionals)
  success                                   = 2
  blocked                                   = 2 (pool 1 SOL/USDC; bin_step=2 tight)
  pool_2_real_quote                         = 10U USDC → 941005 raw X; 20U USDC → 1882010 raw X

paid_rpc_decision
  paid_rpc_required                          = partial (NOT true)
  single_account_path_works                  = yes
  alternative_to_paid_rpc                    = extend bin array coverage 3 → 5-7 arrays (still public RPC)
  pool_2_quote_worked                        = yes (proves single-account path is sufficient for some pools)
  pool_1_quote_blocked_reason                = tight bin_step (2) + 3 arrays insufficient; needs wider coverage

next_stage_decision
  recommended                                = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
  default                                    = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT

key_breakthrough
  v1_v4_blocker                              = multi-account getBinArrayForSwap 403 on public RPC (0/4 quote)
  v5_unblocker                                = single-account path: deriveBinArray + connection.getAccountInfo(singlePubkey)
  v4_to_v5_quote                              = 0/4 → 2/4 (V1-V4 all 0; V5 first real quote)
  paid_rpc_required_v4_claim                  = yes (without trying)
  paid_rpc_required_v5                        = partial (single-account path works; coverage extension is on public RPC)

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

V5 **breakthrough**: Meteora DLMM single-account bin array path **PROVEN** on public RPC (6/6 `getAccountInfo` success; 420 bins decoded; 2/4 quote success — V1-V4 全部 0% quote). 关键 unblock: **用 SDK `deriveBinArray` (pure PDA) + `connection.getAccountInfo(singlePubkey)` 替代 SDK `getBinArrayForSwap` (multi-account)**. V4 multi-account 403 blocker **完全 bypassed**. Real quote data: pool 2 (X/USDC, bin_step=100) 10U USDC → 941005 raw X (≈ 1 X = 10.62 USDC); 20U USDC → 1882010 raw X. Pool 1 (SOL/USDC, bin_step=2) quote blocked: 3 arrays × 70 bins = 210 bins ≈ 4% price range 不够; 下一阶段 fix_repeat 扩 coverage 3 → 5-7 arrays. **paid_rpc_required = partial** (NOT true); single-account path on public RPC 足够大部分情况. 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; repo `node_modules/` **未**创建.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=1c3d8ea; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (14 upstream files from V4) |
| C SDK bin array helper audit | PASS (12 helpers audited; single-account path identified) |
| D bin array PDA derivation | PASS (6/6 deterministic pubkeys; no RPC) |
| E single-account getAccountInfo smoke | **PASS (6/6 success on public RPC; V4 blocker BYPASSED)** |
| F small-batch getMultipleAccounts smoke | SKIPPED (Stage E full success) |
| G bin liquidity decode | PASS (420 bins decoded via SDK) |
| H quote smoke v2 | PARTIAL (2/4; pool 2 success; pool 1 blocked on tight bin_step) |
| I paid RPC requirement decision | PASS (paid_rpc_required=partial; single-account path works) |
| J next-stage decision | PASS (LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT selected) |
| K FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| L tests + safety scan | pending |
| M git publish | pending |

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
  1. (默认) **同意扩展 coverage 3 → 7 arrays** (next fix_repeat 第一步, 仍 public RPC)
  2. (若 7 arrays 仍 2/4) **paid RPC 决策** (Phase 2B)
  3. (optional) **known pool feed 扩展** (5-10 pools; 仍公共 RPC)
  4. (optional) **Raydium CPMM 真 mainnet pid** (P2)
- 不建议直接进 EV preview (quote 2/4 仍 partial)
- 不建议 STOP (2/4 quote + 6/6 bin array + 420 bins decode = 显著进步)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
