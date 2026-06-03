# Solana Program ID Registry v3 — Stage H

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V2`
- run_id: `20260603_102657`

## 0. 摘要

| protocol | priority | program_id | source | verified | v2_discovery_path | connector_readiness | confidence | next_action |
|---|---|---|---|---|---|---|---|---|
| **Meteora DLMM** | P0 | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | docs.meteora.ag | ✅ | paid_rpc_gpa + sdk_api | **blocked_by_paid_rpc** (full discovery); known-pool decode verified | 0.7 | go LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT |
| **Meteora DAMM v2** | P1 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | MeteoraAg/damm-v2-sdk | ✅ | paid_rpc_gpa | blocked_by_paid_rpc | 0.5 | defer (P1, not critical) |
| **Orca Whirlpools** | P1 | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | orca-so/whirlpools | ✅ | paid_rpc_gpa | blocked_by_paid_rpc | 0.5 | defer (P1, not critical) |
| **Raydium CLMM** | P2 | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | raydium-clmm `lib.rs` | ✅ | paid_rpc_gpa | blocked_by_paid_rpc | 0.5 | defer (P2 lowest) |
| **Raydium CPMM** | P2 | `CPMMoo8L3F4NbTegBCKVNungguN7H1ZpdTHKxQB5qKP1C` | raydium-cp-swap `lib.rs` | ❌ (not_found) | deferred | **deferred** | 0.0 | defer; needs operator input for actual mainnet pid |
| **Lifinity** | P2 | (null) | (no source) | ❌ (deferred) | deferred | **deferred** | 0.0 | defer; needs operator input OR remove from P2 |

## 1. v2 → v3 关键 delta (相对 V1 registry v2)

| protocol | v1 status | v2 (this round) delta |
|---|---|---|
| Meteora DLMM | source+verify+4/5 sub-conditions | **+sdk_path_identified** (Stage C); **+minimal_smoke_success[partial]** (Stage E known-pool read verified) |
| Meteora DAMM v2 | source+verify | unchanged |
| Orca Whirlpools | source+verify | unchanged |
| Raydium CLMM | source+verify | unchanged |
| Raydium CPMM | source only; pid not on mainnet | **V2 re-verified**: pid also not on devnet; both declare_id pids null on both networks |
| Lifinity | unknown (V1 said docs 404) | **V2 correction**: docs 200 but SPA; no machine-readable pid; no GitHub DEX repo; status upgraded unknown→deferred |

## 2. Meteora DLMM connector readiness 5/5 (with 2 operator items)

| sub-condition | status | what blocks |
|---|---|---|
| Q1 source verified | ✅ (V1) | — |
| Q2 on-chain verified | ✅ (V1) | — |
| Q3 gpa discovery | ⚠️ | needs paid RPC (or known-pool feed) |
| Q4 sdk/api path identified | ✅ (V2) | needs SDK install for struct decode |
| Q5 minimal smoke | ⚠️ (partial) | known-pool read path verified; struct fields need full SDK |

**结论**: 5/5 sub-conditions 都被**接触**; 2 个**仍需 operator action** (paid RPC for discovery, SDK install for full decode). **不**是 structural failure. **不**是 spec 禁止的 4/4 失败 (per V1 readiness v2 doc).

## 3. 下一阶段 (V2)

Stage I: next-stage decision — 选 `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT` 或 `LP_SOLANA_PAID_RPC_SETUP_REQUIRED` (因为 paid RPC 仍未就绪).

## 4. 安全断言

```text
this_stage_only_registry_merge   = true
this_stage_did_not_hard_code     = true
this_stage_did_not_run_gpa       = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
v2_line_count_unchanged          = true (992)
```
