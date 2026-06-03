# Meteora Known-Pool Read-Only Connector V1 — 总览

```text
stage                                       = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
run_id                                      = 20260603_134202
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = fa4e5e4 (V3 commit)

known_pool_connector
  built                                     = true
  script                                    = scripts/lp_meteora_dlmm_known_pool_connector_v1_readonly.js
  modes                                     = snapshot | quote-smoke | all
  sdk                                       = @meteora-ag/dlmm@1.9.10
  sdk_install_in_isolated_tmp               = true
  repo_node_modules_created                 = false
  wallet_adapter_imported                   = false
  keypair_instantiated                      = false
  position_creation_methods_called          = false
  swap_tx_builder_called                    = false
  sendTransaction_called                    = false

known_pool_count                            = 2
  pool_1 (5BKxfWMb swap_quote.ts)           = SOL/USDC bin_step=2 active_bin=-12248 fee=0.02%/10% reserves=49.4B/1.06B
  pool_2 (9DiruRpj lock_info.ts)            = X/USDC bin_step=100 active_bin=-236 fee=1.5%/10% reserves=101T/2.2T

pool_snapshot_success_count                 = 2/2 (full LbPair decode via DLMM.create + getActiveBin)
fee_snapshot_success_count                  = 2/2 (base + max via dlmmPool.getFeeInfo)
bin_liquidity_snapshot_success_count        = 0/2 (blocked: getBinArrayForSwap 403 on public RPC)
quote_snapshot_success_count                = 0/4 (blocked: depends on bin arrays)

6-table readiness
  known_pool_universe_v1                    = ready
  pool_snapshot_v1                          = ready
  fee_snapshot_v1                           = ready
  bin_liquidity_snapshot_v1                 = blocked_public_rpc
  quote_snapshot_v1                         = blocked_public_rpc
  survival_ev_preview_v1                    = blocked_missing_quote

judgments
  connector_readonly_ready                  = yes (3/6 tables ready)
  quote_ready                               = no
  survival_ev_ready                         = no
  needs_paid_rpc                            = yes (to unblock bin + quote + EV)
  needs_known_pool_feed_expansion           = no (2 pools sufficient for V4 validation)

next_stage_decision
  recommended                               = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
  default                                   = LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT
  alternative_if_single_account_fails       = LP_SOLANA_PAID_RPC_SETUP_REQUIRED

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

V4 在 V3 基础上固化 Meteora DLMM known-pool read-only connector V1: **(1) 写 reusable connector script** (`lp_meteora_dlmm_known_pool_connector_v1_readonly.js`) 支持 `--mode snapshot/quote-smoke/all`, --known-pool-feed, --output-dir, --run-id, --rpc-url-redacted-source; SDK 复用 V3 在 /tmp 隔离 install; **不** import wallet-adapter; **不** instantiate Keypair; **不**调 pos-create / tx-builder; **(2) 2/2 known pools full LbPair decode** (real on-chain state): pool 1 = SOL/USDC bin_step=2 active_bin=-12248 fee=0.02%/10% reserves 49.4B/1.06B; pool 2 = X/USDC bin_step=100 active_bin=-236 fee=1.5%/10% reserves 101T/2.2T; **(3) 6-table readiness 判定** (3 ready / 2 blocked_public_rpc / 1 blocked_missing_quote) — connector V1 工作, quote/EV 阻隔是 public RPC 限制; **(4) 下一阶段** = `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT` (试 single-account bin array path, 失败则 paid RPC); 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; repo `node_modules/` **未**创建.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=fa4e5e4; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (14 upstream files from V3) |
| C connector script | PASS (reusable; no signer; no sendTransaction; no wallet adapter) |
| D known pool universe | PASS (2 pools selected; full addresses from V3 artifact) |
| E pool snapshot | PASS (2/2 full LbPair decode; real on-chain state) |
| F fee snapshot | PASS (2/2 base + max via SDK getFeeInfo) |
| G bin liquidity attempt | BLOCKED (0/2; 403 on public RPC; root cause documented) |
| H quote attempt | BLOCKED (0/4; depends on bin arrays) |
| I readiness matrix | PASS (6 tables judged; 3 ready / 2 blocked / 1 blocked_missing) |
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
  1. **是否同意 single-account bin array path 试一次** (next fix_repeat 第一步)
  2. (若 single-account path 失败) **paid RPC 决策** (Phase 2B; Helius / Triton / QuickNode)
  3. (optional) **known pool feed 扩展** (5-10 pools; 仍走公共 RPC)
  4. (optional) **Raydium CPMM 真 mainnet pid** (P2; 不在 Meteora DLMM critical path)
- 不建议改选 EV preview (quote 缺数据)
- 不建议 STOP (3/6 tables ready; 2/2 pools decoded; connector V1 工作)
- 即便选 fix_repeat, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
