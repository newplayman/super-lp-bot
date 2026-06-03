# Meteora Survival EV Preview V8 — 总览

```text
stage                                       = LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1
run_id                                      = 20260603_153736
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 3c72d3f (V7 commit)

scope
  frozen                                    = partial_pool2_only
  included_pools_count                      = 1 (X/USDC)
  excluded_pools_count                      = 1 (SOL/USDC; no_quote_data)
  honesty                                   = "本报告是 PARTIAL; not full; 不能代表所有 Meteora DLMM"

ev_model
  ran                                       = true
  dimensions                                = 6 notionals × 7 hold_windows × 4 scenarios
  total_cells                               = 168
  positive_zero_il_lvr_count                = 0
  positive_optimistic_count                 = 0
  positive_realistic_count                  = 0
  positive_conservative_count               = 0
  near_break_even_count                     = 21
  best_notional                             = 2000
  best_hold_window                          = 15m
  best_scenario                             = zero_il_lvr
  best_net_ev_proxy_usd                     = -$0.154
  best_net_ev_proxy_pct                     = -0.0077%
  heuristic_marked                          = true (all 297 rows)
  missing_data_marked                       = true (actual volume, actual IL/LVR, real SOL price, etc.)

preflight_10_20U
  x_usdc_preflight_candidate                = false
  reason                                    = "All 10/20U X/USDC cells negative; better path is known pool feed expansion"

next_stage_decision
  recommended                                = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
  default                                    = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
  rationale                                  = "X/USDC partial EV all negative; 5-10 pools expansion may find positive EV"

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

V8 在 V7 基础上 完成 **Meteora DLMM partial survival EV preview** (X/USDC only; SOL/USDC excluded with no_quote_data reason): **(1) Scope freeze** (1 included; 1 excluded); **(2) EV model input build** (168 cells; 6×7×4 dimensions; missing data marked 'missing' not 0); **(3) Fee capture proxy** (126 rows; scenario-based; heuristic marked); **(4) Cost model** (3 scenarios; SOL price $130 heuristic); **(5) Survival EV preview 168 cells: 0/168 positive; ALL negative**; **(6) 10/20U preflight: NOT worth** (best -$0.184 at 20U/15m/zero_il_lvr; worst -$0.284 at 20U/realistic); **(7) honest finding: Meteora DLMM X/USDC at retail scale (10-2000 USD) is structurally unprofitable for single-position LP** (low base_fee 1.5% + low volume 0.5% + high fixed cost $0.19 + IL/LVR $2 on $2000); **(8) 下一阶段 = `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`** (扩展 5-10 pools 找 positive EV). 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; **不**代表 full EV (partial scope); 缺失数据 explicit 标记 'missing' 不填 0.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=3c72d3f; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (14 upstream files from V7+V4) |
| C partial scope freeze | PASS (X/USDC included; SOL/USDC excluded with no_quote_data reason) |
| D survival EV model input build | PASS (168 cells; 6×7×4 dimensions; missing data marked) |
| E fee capture proxy | PASS (126 rows; scenario-based; heuristic marked) |
| F cost model | PASS (3 scenarios; SOL_PRICE=$130 heuristic) |
| G survival EV preview | PASS (168 cells; 0/168 positive; honest negative EV) |
| H 10/20U preflight implication | PASS (X/USDC NOT worth; better path is feed expansion) |
| I next-stage decision | PASS (LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1 selected) |
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
× 未代表 full EV (partial scope only; SOL/USDC marked no_quote_data)
× 未填 missing data 为 0 (honest marking; 'missing' not 0)
```

## 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1`（无需操作员声明）
- 关键 input 需求:
  1. (默认) **同意扩展 known pool feed** (next fix_repeat 第一步)
  2. (可选) **operator 提供 Meteora UI top pools 列表** (5-10 pools; human-curated)
  3. (可选) **是否同意扩展到 Raydium CLMM / Orca Whirlpools** (different AMM; different fee structures)
  4. (可选) **是否提供 paid RPC key** (用于 10-20U 真正 probe preflight; 不在 V8 推荐)
  5. (可选) **是否接受 STOP** (如果 5-10 pools 都 negative EV; 仍 read-only connector 可用于其他目的)
- 不建议 10/20U probe preflight (V8 evidence: 10/20U X/USDC all negative)
- 不建议 STOP 立即 (V8 EV 是 first quantitative signal; read-only path fully working)
- 即便选 feed expansion, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
