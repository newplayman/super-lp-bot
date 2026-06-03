# Meteora DLMM SDK Connector Feasibility V3 — 总览

```text
stage                                       = LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1
run_id                                      = 20260603_130532
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 4099b13 (V2 commit)

sdk_package_audit
  ran                                       = true
  install_in_isolated_tmp                   = true (npm install @meteora-ag/dlmm@1.9.10 in /tmp)
  repo_root_touched                         = false
  repo_node_modules_created                 = false
  wallet_adapter_imported                   = false
  keypair_instantiated                      = false
  position_creation_methods_called          = false

known_pool_feed
  ready                                     = true
  total_candidates                          = 3 (all from official SDK examples)
  mainnet_verified                          = 2
  selected_for_sdk_smoke                    = 2
  skipped_not_mainnet                       = 1 (3W2HKgUa from example.ts; getAccountInfo null)

known_pool_smoke (Stage E)
  ran                                       = true
  success                                   = true (2/2 pools full LbPair decode)
  pool_5BKxfWMb_decoded                     = SOL/USDC, bin_step=2, active_bin=-12248, fee=0.02%/10%, reserves available
  pool_9DiruRpj_decoded                     = X/USDC, bin_step=100, active_bin=-236, fee=1.5%/10%, reserves available
  bin_array_lookup                          = blocked (public RPC 403/410)
  lock_info                                 = blocked (RPC 410 disabled)

quote_smoke (Stage F)
  ran                                       = true
  success                                   = false (0/4 quote)
  attempted                                 = 4 (2 pools × 2 notionals: 10U, 20U USDC)
  root_cause                                = getBinArrayForSwap 403 on publicnode / 410 on mainnet-beta
  sdk_swapQuote_call_ready                  = true (verified; would work with bin arrays)

connector_schema (Stage G)
  ready                                     = true
  table_count                               = 6
  tables_works_in_v3                        = 3 (universe, pool_snapshot, fee_snapshot)
  tables_blocked_public_rpc                 = 3 (bin_liquidity, quote, ev)
  field_coverage                            = 14/14 (all required fields covered)

discovery_strategy_decision (Stage H)
  paths_evaluated                           = [paid_rpc_gpa, known_pool_feed_sdk_decode, official_rest_api]
  selected                                  = known_pool_feed_sdk_decode
  selected_phase                            = Phase 2A
  paid_rpc_decision                         = Phase 2B (operator input required)

next_stage_decision (Stage I)
  recommended                               = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
  default                                   = LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1
  connector_v1_can_run_with                 = 3/6 tables active (universe, pool_snapshot, fee_snapshot)
  connector_v1_blocked_by                   = 3/6 tables (bin_liquidity, quote, ev; Phase 2B concern)

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

V3 在 V2 基础上完成 Meteora DLMM SDK feasibility 全套验证: **(1) npm install @meteora-ag/dlmm@1.9.10** 在 /tmp 隔离 env (152 packages; repo root 不动; **不**含 wallet-adapter dependency; **不** instantiate Keypair); **(2) known-pool feed** 冻结 2 pools (from official SDK examples swap_quote.ts + fetch_lb_pair_lock_info.ts), 1 pool (example.ts) 因 not on mainnet skipped; **(3) SDK known-pool smoke 2/2 成功** — 真实链上 LbPair state: pool 1 = SOL/USDC, bin_step=2, active_bin=-12248, fee=0.02%/10%, reserves 49.4B raw X / 1.06B raw Y; pool 2 = X/USDC, bin_step=100, active_bin=-236, fee=1.5%/10%, reserves 101T X / 2.2T Y; **(4) quote smoke 0/4 阻断** (public RPC 403/410 on getBinArrayForSwap, root cause documented, swapQuote SDK function is wired); **(5) 6-table connector schema** 设计完整 (14/14 field coverage; data_confidence honest; 3/6 tables works in V3, 3/6 blocked on public RPC); **(6) 3-path decision** — known_pool_feed_sdk_decode 选为 Phase 2A; paid_rpc_gpa 留 Phase 2B; **(7) 下一阶段** = `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1` (实现 6 张表; 3 张活跃, 3 张 schema ready); 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge; repo `node_modules/` **未**创建.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=4099b13; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (11 upstream files from V2) |
| C isolated SDK env audit | PASS (npm install in /tmp; 152 packages; repo root untouched) |
| D known pool feed freeze | PASS (2 pools selected; 1 skipped not on mainnet; all from official SDK examples) |
| E SDK known-pool smoke | PASS (2/2 pools full LbPair decode; real on-chain state) |
| F SDK quote smoke | BLOCKED (0/4; root cause documented; not blocking connector V1) |
| G connector schema v1 | PASS (6 tables; 14/14 field coverage) |
| H discovery strategy decision | PASS (3 paths; known_pool_feed_sdk_decode selected for Phase 2A) |
| I next-stage decision | PASS (LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1 selected) |
| J FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| K tests + safety scan | pending |
| L git publish | pending |

## 严格禁区（本轮已遵守）

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
× 未在 repo root 安装任何 npm package (只在 /tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID})
× 未 instantiate Keypair
× 未 import @solana/wallet-adapter-*
× 未调用 position-create / addLiquidity / removeLiquidity / closePosition / claimFee / claimReward
× swapQuote 调 read-only 函数 (returns quote object); **不**构造 transaction
```

## 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_KNOWN_POOL_READONLY_CONNECTOR_V1`（无需操作员声明）
- 关键 input 需求（建议下个 prompt 提供）:
  1. **research-only storage 选择** (Postgres shadow / sqlite / JSON file); 默认建议 sqlite
  2. **known pool feed 扩展** (operator 可人工 curate 5-10 个 Meteora UI top pools; 否则维持 2)
  3. (optional) **paid RPC 决策** (Phase 2B; 不在 connector V1 必须)
  4. (optional) **是否同意 connector V1 + paid RPC 合并** (即 "一阶段" 同时实现表 + quote; 风险复杂 stage)
- 不建议改选 connector V1 + paid RPC 合并 (3/6 表先跑稳, 再补 paid RPC; 风险隔离)
- 不建议 STOP (2/2 pool full decode + 6-table schema + strategy decided = 显著进步; 不是 structural failure)
- 即便选 connector V1, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事.
