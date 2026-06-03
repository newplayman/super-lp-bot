# Solana LP Connector Design — 总览

```text
stage                                       = LP_SOLANA_LP_CONNECTOR_DESIGN_V1
run_id                                      = 20260603_080347
status                                      = PASS
branch                                      = feat/supabase-postgres-deployment
head_before                                 = e4deffb (LP_MULTICHAIN_DEX_LP_DISCOVERY_AND_SURVIVAL_EV_V1)

evm_v3_path_paused                          = true
solana_connector_design_complete            = true

target_protocols
  p0_protocol                               = Meteora DLMM
  p1_protocols                              = [Orca Whirlpools, Meteora DAMM v2]
  p2_protocols                              = [Raydium CLMM, Raydium CPMM, Lifinity]
  target_protocol_count                     = 6

design artifacts
  schema_proposal_ready                     = true   (7 tables; 20 spec fields all covered)
  survival_ev_adaptation_ready              = true   (EVM V3 reuse framework; Solana-specific cost model)
  probe_preflight_design_ready              = true   (12 gates; read-only design)
  implementation_roadmap_ready              = true   (6 phases + 3 future execution stages)

heuristic_expected_net_ev_at_$10_7d
  EVM_V3_Base_realistic                     = -$0.046  (upstream model)
  Solana_Meteora_DLMM_optimistic            = +$0.01 to +$0.05  (heuristic; needs read-only verification)
  Solana_Orca_Whirlpools_optimistic         = +$0.005 to +$0.02  (heuristic)
  note                                       = heuristic only; needs actual fee/IL data via Phase 1-4

round_trip_cost_usd_comparison
  EVM_Base_V3                               = $0.012
  Solana_Meteora_DLMM                       = $0.0031
  Solana_Orca_Whirlpools                    = $0.0048

recommended_next_stage                      = LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1
allowed_next_stages                         = LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1
                                                LP_METEORA_DLMM_READONLY_CONNECTOR_V1
                                                LP_SOLANA_LP_CONNECTOR_DESIGN_FIX_REPEAT
                                                STOP_LP_RESEARCH_NOW

safety locks (all intact)
  can_run_probe_now                          = false
  execution_allowed_now                      = false
  tiny_canary_allowed                        = "no"
  edge_proven                                = "no"
  wallet_or_tx_touched                       = false
  solana_wallet_or_keypair_touched           = false
  private_key_loaded                         = false
  sendTransaction_called                    = false
  sendRawTransaction_called                 = false
  approve_executed                           = false
  mint_executed                              = false
  decrease_executed                         = false
  collect_executed                          = false
  burn_executed                              = false
  swap_executed                              = false
  bridge_called                              = false
  live_started                               = false
  canary_started                             = false
  paper_started                              = false
  any_funds_spent                            = false
  v2_line_count_unchanged                    = true (992)
```

## 一句话

EVM V3 范式已实证失败 (上游 0/19,980 positive EV)；本阶段设计了 6 个 Solana LP 协议 (P0 Meteora DLMM / P1 Orca Whirlpools+Meteora DAMM v2 / P2 Raydium+Lifinity)、7 张 normalized schema、EVM V3 survival EV model 的 Solana-specific 适配、12-gate read-only 10/20U probe preflight design、和 6-phase + 3-future-stage implementation roadmap；下一阶段 = **LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1**（最低风险入口，先确认 public RPC + 4 个 protocol program pubkey 可用）；本阶段**未**实现任何 connector 代码、**未**跑任何 RPC、**未**读任何 Solana wallet/keypair/private key、**未**签名 / **未**发任何 transaction、**未**碰任何 LP / swap / bridge / live/canary/paper。

## 阶段验收

| 阶段 | 状态 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (10 upstream files) |
| C Solana protocol target matrix | PASS (6 protocols; P0/P1/P2) |
| D Solana data source feasibility | PASS (RPC + 5 indexers/APIs) |
| E Meteora DLMM connector design | PASS (bin-based; preflight) |
| F Orca Whirlpool connector design | PASS (tick array; NFT position) |
| G Raydium connector design | PASS (CLMM + CPMM; P2) |
| H Solana LP schema proposal | PASS (7 tables; 20 spec fields) |
| I Solana survival EV model adaptation | PASS |
| J Solana 10/20U probe preflight design | PASS (12 gates) |
| K implementation roadmap | PASS (6 phases + 3 future) |
| L FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX | (this file) |
| M tests + safety scan | pending |
| N git publish | pending |

## 严格禁区（本轮已遵守）

```text
× 未读 Solana 私钥 / seed phrase / keypair
× 未创建 signer
× 未发送 Solana transaction
× 未调用 swap / open_lp / close_lp / collect_fee
× 未启动 live / canary / paper
× 未桥接
× 未自动换币
× 未写 production positions / shadow tables
× 未修改 EVM executor v2 (line count 仍 992)
× send hard-disable 仍存在（未解除）
× 6 protocol × 7 table × 12-gate × 6-phase 仅 design doc
```

## 操作员后续

- 默认下一阶段 = `LP_SOLANA_READONLY_RPC_AND_REGISTRY_V1`（无需操作员声明）
- 可选改：
  - `LP_METEORA_DLMM_READONLY_CONNECTOR_V1`（直接进 Meteora DLMM connector；跳 Phase 1）
  - `LP_SOLANA_LP_CONNECTOR_DESIGN_FIX_REPEAT`（修复/补 design）
  - `STOP_LP_RESEARCH_NOW`（彻底停）
- 即便选 Meteora DLMM connector 阶段，仍需新一轮 prompt 显式确认；本阶段**未**自动做这件事。
- **任何**未来阶段都不得直接发 tx；必须仍走 12-gate preflight + 显式 operator approval + 2 phrase 双重确认。
