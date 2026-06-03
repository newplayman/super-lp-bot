# Solana RPC Registry Fix Repeat V2 — 总览

```text
stage                                       = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2
run_id                                      = 20260603_102657
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 2ca2ab6

meteora_dlmm_sdk_api_source_discovery
  discovery_ran                             = true
  sdk_package                               = @meteora-ag/dlmm v1.9.10
  github_repo                               = MeteoraAg/dlmm-sdk (ts-client)
  api_endpoint                              = none_found (dlmm-api.meteora.ag 404 on all paths)
  sdk_decode_for_known_pool                 = yes (DLMM.create + getActiveBin + swapQuote + getLbPairLockInfo + getBinArray + getFeeInfo)
  sdk_discovery                             = partial (getLbPairs internally uses GPA; SDK does NOT bypass GPA)

meteora_dlmm_discovery_path_decision
  paths_evaluated                           = [public_rpc_gpa, paid_rpc_gpa, official_sdk_api]
  recommended_discovery_path                = paid_rpc_gpa
  fallback_path                             = official_sdk_api (decode/quote of known pool)
  public_rpc_gpa_0_4_in_v1                   = confirmed not_feasible
  paid_rpc_gpa                              = likely_feasible; needs operator key
  official_sdk_api                          = partial (decode yes; discovery no)

meteora_dlmm_minimal_smoke
  smoke_ran                                 = true
  smoke_success                             = true (partial)
  smoke_path                                = known_pool_read (swap_quote.ts example)
  first_pool_address                        = 5BKxfWMbmYBAEWvyPZS9esPducUba9GqyMjtLCfbaqyF
  pool_owner                                = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo (Meteora DLMM)
  data_len_bytes                            = 904 (matches LbPair struct)
  struct_fields_extracted                   = false (needs full TypeScript SDK)
  latency_ms                                = 199

raydium_cpmm_pid_fix
  v1_finding                                = not_found on mainnet
  v2_re_verify                              = not_found on mainnet AND devnet (both declare_id pids null on both networks)
  raydium_cpmm_pid_fixed                    = false
  raydium_cpmm_status                       = deferred

lifinity_pid_decision
  v1_finding                                = unknown (V1 said docs 404)
  v2_correction                             = docs 200 but SPA; no machine-readable pid; no public GitHub DEX repo
  lifinity_status                           = deferred

registry_v3
  count                                     = 6
  verified_count                            = 4 (Meteora DLMM, DAMM v2, Orca, Raydium CLMM)
  not_found_count                           = 1 (Raydium CPMM)
  deferred_count                            = 1 (Lifinity)

meteora_dlmm_sub_conditions (5/5 touched)
  Q1_source_verified                        = yes (V1)
  Q2_onchain_verified                       = yes (V1)
  Q3_gpa_discovery                          = blocked (public RPC 0/4; needs paid RPC or known-pool feed)
  Q4_sdk_api_path_identified                = yes (V2 stage C)
  Q5_minimal_smoke                          = partial (V2 stage E: known-pool read verified; struct fields not extracted)

improvement_vs_v1
  meteora_dlmm_q4_v1                        = partial
  meteora_dlmm_q4_v2                        = yes (full SDK path)
  meteora_dlmm_q5_v1                        = no
  meteora_dlmm_q5_v2                        = partial (known-pool read verified)
  rpc_decision_v1                           = not_decided
  rpc_decision_v2                           = paid_rpc_gpa (with sdk_api fallback)

recommended_next_stage                      = LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT
allowed_next_stages                         = LP_METEORA_DLMM_READONLY_CONNECTOR_V1
                                                LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT
                                                LP_SOLANA_PAID_RPC_SETUP_REQUIRED
                                                LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
                                                STOP_LP_RESEARCH_NOW

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

V2 在 V1 基础上确认 3 件事: (1) Meteora DLMM 官方 SDK (`@meteora-ag/dlmm` v1.9.10) 路径**已找到** (Stage C); 6 sources verified, 1 unknown (Meteora API endpoint 404). (2) 3 条 discovery 路径 (public_rpc_gpa / paid_rpc_gpa / official_sdk_api) 已评估; **推荐 paid_rpc_gpa** (with `official_sdk_api` as fallback for known pool decode/quote); SDK 不替代 GPA — 它对**已知 pool** decode/quote 工作得很好, 对**首次 discovery** 仍需 GPA. (3) Known-pool read-only smoke (Stage E) 验证: pool account 存在 + owner = Meteora DLMM program + data_len = 904 bytes (matches LbPair struct); latency 199ms; struct 字段 decode 需要 full TypeScript SDK (out of scope this round). Raydium CPMM mainnet pid `CPMMoo8L...` 仍 not on mainnet (V2 re-verified: not on devnet either). Lifinity docs 是 SPA, 找不到 machine-readable pid. 下一阶段 = `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT` (wire SDK + decide paid RPC); 本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge.

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS (HEAD=2ca2ab6; pre-existing dirty files unrelated) |
| B input evidence audit | PASS (14 upstream files) |
| C SDK/API source discovery | PASS (6 sources verified: SDK package, DLMM class, getLbPairs, DLMM.create, swapQuote example, lock_info example; 1 unknown: dlmm-api.meteora.ag) |
| D discovery path decision | PASS (3 paths evaluated; paid_rpc_gpa recommended; sdk_api as fallback) |
| E minimal read-only smoke | PARTIAL (known-pool read path verified; struct decode needs full SDK) |
| F Raydium CPMM mainnet pid fix | DEFERRED (pid not on mainnet AND devnet; both declare_id pids null) |
| G Lifinity pid decision | DEFERRED (docs SPA; no public GitHub DEX repo) |
| H registry v3 | PASS (4 verified + 1 not_found + 1 deferred) |
| I next stage decision | PASS (LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT selected) |
| J FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| K tests + safety scan | pending |
| L git publish | pending |

## 严格禁区（本轮已遵守）

```text
× 未读 Solana 私钥 / seed phrase / keypair / wallet adapter
× 未创建 signer
× 未构造 transaction
× 未调用 sendTransaction
× 未调用 swap / open_lp / close_lp / collect_fee
× 未启动 live / canary / paper
× 未桥接 / 自动换币
× 未写 production positions / shadow 表
× 未修改 EVM executor v2 源码
× send hard-disable 仍存在（未解除）
× 未 hard-code 任何 protocol program id (除文档/源码 引用)
× 未 webfetch blog / Twitter / 论坛 / unofficial GitHub
× 未调 Meteora /swap
× 未 paid RPC call (无 key)
× 未 npm install @meteora-ag/dlmm (Stage E 用了 stdlib-only Python 替代)
```

## 操作员后续

- 默认下一阶段 = `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT`（无需操作员声明）
- 关键 input 需求 (建议下个 prompt 提供):
  1. **paid RPC 决策** (Helius / Triton / QuickNode; 或 维持 public only + known-pool feed)
  2. **是否同意 connector 走"known-pool feed + SDK decode"路径** (而非 paid RPC GPA for first-time discovery)
  3. (optional) **Raydium CPMM 真 mainnet pid** (从 operator 人类来源)
  4. (optional) **Lifinity pid** (从 operator 浏览器渲染 docs) **OR 同意从 P2 列表移除**
- 不建议改选 connector V1 (5/5 conditions touched 但 2 仍需 operator action)
- 不建议 STOP (5/6 source + 4/6 verified + sdk path identified + known-pool read smoke works = 显著进步)
- 即便选 connector V1, **仍需**新一轮 prompt 显式确认; 本阶段**未**自动做这件事。
