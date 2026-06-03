# Solana RPC Registry Fix Repeat — 总览

```text
stage                                       = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1
run_id                                      = 20260603_093136
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = 9c46813

oficial_source_discovery
  discovery_ran                             = true
  discovery_method                          = WebFetch + curl github raw
  oficial_program_id_count                  = 5
  unknown_count                              = 1
  sourced_protocols                          = [Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM, Raydium CPMM]
  still_unknown                              = [Lifinity]

onchain_verification
  verified_program_count                    = 4
  verified_protocols                        = [Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM]
  not_found                                  = [Raydium CPMM (cp-swap declare_id! not on mainnet)]
  skipped (no pid)                          = [Lifinity]

gpa_smoke
  attempted_count                          = 4
  success_count                             = 0
  blocker                                  = public RPC not feasible for any major AMM (timeout / -32010 / 429)

readiness (5 protocols with sources; 1 still unknown)
  Meteora_DLMM                              = 4/5 sub-conditions; only GPA blocked; near-ready if paid RPC or indexer
  Meteora_DAMM_v2                           = 2/5; GPA + SDK blocked
  Orca_Whirlpools                            = 2/5; GPA + SDK blocked
  Raydium_CLMM                              = 2/5; GPA + SDK blocked
  Raydium_CPMM                              = 1/5; pid not on mainnet (real on-chain finding)
  Lifinity                                  = 0/5; pid unknown

key_findings
  ✓ 5/6 protocol pids obtained from official sources (was 0/6 last round)
  ✓ 4/6 verified on-chain via getAccountInfo (was 0/6 last round)
  ✗ 0/4 GPA success on public RPC (dataSlice 0; timeout / -32010 / 429)
  ✗ Raydium CPMM pid from cp-swap declare_id! is NOT on mainnet (need raydium-amm-v3 pid)
  ✗ Lifinity pid remains unknown (docs 404; no public source)

recommended_next_stage                      = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
allowed_next_stages                         = LP_METEORA_DLMM_READONLY_CONNECTOR_V1
                                                LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1
                                                LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
                                                LP_SOLANA_RPC_SETUP_REQUIRED
                                                STOP_LP_RESEARCH_NOW

safety locks (all intact)
  can_run_probe_now                          = false
  execution_allowed_now                      = false
  transaction_sent                          = false
  wallet_or_tx_touched                       = false
  solana_wallet_or_keypair_touched           = false
  tiny_canary_allowed                        = "no"
  edge_proven                                = "no"
  hard_disable_still_active                  = true
  v2_line_count_unchanged                    = true (992)
```

## 一句话

5/6 protocol pids 已从 **官方来源** 获得 (docs.meteora.ag / github MeteoraAg / github orca-so / github raydium-io 仓库 `declare_id!` 宏)；4/6 (Meteora DLMM, Meteora DAMM v2, Orca Whirlpools, Raydium CLMM) 通过链上 `getAccountInfo` 验证 (executable=true, BPFLoaderUpgradeable)；但 (1) Raydium CPMM 的 cp-swap `declare_id!` 在 mainnet 不可验证 (pid not on mainnet; 推测需用 raydium-amm-v3 源) (2) GPA 在 public RPC 上对所有 4 个主流量级 AMM 不可行 (timeout / program too large / rate-limited) (3) SDK / API paths 设计但未 wire；下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT` 需修 (a) Raydium CPMM 真 pid, (b) 决策 paid RPC vs indexer vs SDK-only；本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发 tx / **未** open LP / swap / bridge。

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (10 upstream files) |
| C oficial source discovery | PASS (5/6 sourced via WebFetch + curl) |
| D program id registry v2 | PASS (5 official + 1 unknown; conflict detection) |
| E onchain verification v2 | PASS (4 verified + 1 not_found + 1 skipped) |
| F bounded GPA smoke v2 | PASS (0/4 success; blocker documented) |
| G Meteora DLMM readiness v2 | WARN (4/5 sub-conditions; GPA blocked) |
| H P1/P2 readiness v2 | WARN (5/6 partial; 0 fully ready) |
| I next stage decision | PASS (FIX_REPEAT selected) |
| K FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| L tests + safety scan | pending |
| M git publish | pending |

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
× 未调 Jupiter /swap
× 未调任何 SDK / indexer / API
```

## 操作员后续

- 默认下一阶段 = `LP_SOLANA_RPC_REGISTRY FIX_REPEAT`（无需操作员声明）
- 候选 fix_repeat 行动:
  1. **提供 Raydium CPMM 真 mainnet pid** (从 raydium-amm-v3 仓库或 Raydium 官方 docs)
  2. **决策 paid RPC vs indexer vs SDK-only**: 是否接受 Helius/Triton/QuickNode (paid) 用于 connector stage 的 GPA
  3. (optional) **Lifinity pid**: 人类来源 (不在主路径; OK to defer)
  4. (optional) **是否同意 connector stage 直接 wire SDK + 选 paid RPC in one stage** (而非再 fix_repeat)
- 不建议改选 connector (4/5 sub-conditions; GPA blocked; SDK not wired; 1 not_found)
- 不建议 STOP (5/6 source + 4/6 verified 是显著进步; 不是 structural failure)
- 即便选 connector stage，**仍需**新一轮 prompt 显式确认；本阶段**未**自动做这件事。
