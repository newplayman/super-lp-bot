# Solana Read-Only RPC + Registry — 总览

```text
stage                                       = LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1
run_id                                      = 20260603_084054
status                                      = WARN
branch                                      = feat/supabase-postgres-deployment
head_before                                 = bf92f4c (LP_SOLANA_LP_CONNECTOR_DESIGN_V1)

solana_rpc_readiness                        = true
usable_rpc_count                            = 2
primary_endpoint_id                        = public_publicnode-110e5a18
primary_avg_latency_ms                     = 314.54
rpc_methods_verified                       = 8/8 (Health, Version, Slot, BlockHeight, LatestBlockhash, EpochInfo, GenesisHash, AccountInfo)

protocol_registry_seed                      = true
registry_count                              = 6
p0_protocol                                 = Meteora DLMM
p1_protocols                                = [Orca Whirlpools, Meteora DAMM v2]
p2_protocols                                = [Raydium CLMM, Raydium CPMM, Lifinity]
hard_coded_program_id_count                 = 0  (per spec no-hard-code policy)

program_verification                        = path verified (System Program sanity); 0 protocol pids verified this round
gpa_path_sanity                             = verified (System Program); 0 protocol GPA smoke (no pid)

token_quote_reference_design                = 9/9 dimensions designed (SPL metadata, decimals, Jupiter Quote, balance, SOL/USD, USDC, wSOL, mint registry, pool validation)

meteora_dlmm_registry_ready                 = false (3/4 connector conditions fail)
orca_registry_ready                         = false (pid missing)
damm_v2_registry_ready                      = false (pid missing)

recommended_next_stage                      = LP_SOLANA_RPC_REGISTRY_FIX_REPEAT
allowed_next_stages                         = LP_METEORA_DLMM_READONLY_CONNECTOR_V1
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
  private_key_loaded                         = false
  sendTransaction_called                    = false
  any_funds_spent                            = false
  v2_line_count_unchanged                    = true (992)
```

## 一句话

Solana read-only RPC 路径**完整可用**（2/2 public RPC usable; 8/8 method verified; System Program sanity OK）；但 6 protocol program id **故意不填**（spec 禁止凭记忆硬编码），导致 0/6 protocol 进 on-chain verify / GPA smoke / readiness；fix_repeat stage 需先**外部**获取 6 个官方 program id 后才能进 Phase 2 connector；下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`；本阶段**未**接 wallet / **未**读 keypair / **未**签名 / **未**发任何 transaction / **未** swap / bridge / open_lp / close_lp / collect_fee。

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (14 upstream files) |
| C RPC readiness matrix | PASS (2/2 endpoints; 8/8 methods) |
| D protocol registry seed | PASS (6 protocols; 0 hard-coded pids) |
| E program ID verification | PASS (path verified; 0/6 protocol pids to verify) |
| F account discovery feasibility | PASS (path verified; 0/6 GPA smoke) |
| G token/quote reference design | PASS (9 dimensions) |
| H Meteora DLMM readiness | WARN (3/4 conditions fail) |
| I Orca + DAMM readiness | WARN (0/4 conditions each) |
| J next stage decision | PASS (FIX_REPEAT selected) |
| K FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| L tests + safety scan | pending |
| M git publish | pending |

## 严格禁区（本轮已遵守）

```text
× 未读 Solana 私钥 / seed phrase / keypair / wallet adapter
× 未创建 signer
× 未构造 transaction
× 未调用 sendTransaction
× 未调用 swap
× 未 open_lp / close_lp / collect_fee
× 未 bridge
× 未启动 live / canary / paper
× 未写 production positions
× 未覆盖 shadow 表
× 未修改 EVM executor v2 源码
× send hard-disable 仍存在（未解除）
× 未 hard-code 任何 protocol program id (per spec)
× 未 webfetch 任何外部文档 (留 fix_repeat)
× 未调任何 SDK / indexer / API
× 未调 Jupiter Quote
```

## 操作员后续

- 默认下一阶段 = `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT`（无需操作员声明）
- 候选 fix_repeat 行动：
  1. 人类从 Meteora/Orca/Raydium 官方 docs 获取 6 个 program id
  2. 或允许 fix_repeat stage 启用 webfetch 工具 (建议人类提供 pid list 更可靠)
  3. fix_repeat stage 重跑 Stages D-I
- 不建议改选 connector (3/4 条件不满足)
- 不建议 STOP (data gap 是 temporary, not structural)
- 即便 fix_repeat 成功，**仍需**新一轮 prompt 显式确认；本阶段**未**自动做这件事。
