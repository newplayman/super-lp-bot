# Solana Program ID Registry v2 — Stage D

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 摘要

| protocol | program_id | source | verified | selected_for_onchain |
|---|---|---|---|---|
| **Meteora DLMM** | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | docs.meteora.ag | ✅ | ✅ |
| **Meteora DAMM v2** | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | github.com/MeteoraAg/damm-v2-sdk | ✅ | ✅ |
| **Orca Whirlpools** | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | github.com/orca-so/whirlpools | ✅ | ✅ |
| **Raydium CLMM** | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | raydium-clmm `lib.rs` declare_id! | ✅ | ✅ |
| **Raydium CPMM** | `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` | raydium-cp-swap `lib.rs` declare_id! | ✅ | ✅ |
| **Lifinity** | (unknown) | docs.lifinity.io 404 | ❌ | ❌ |

## 1. 来源与冲突检查

- 5 verified 协议**无**多源冲突
- 2 Raydium 协议有 devnet `secondary_program_id_devnet`；**显式标记** mainnet vs devnet
- Lifinity 维持 unknown (per spec "no memory hardcode")

## 2. 规则 (per spec)

> "只有 oficial_source_verified = yes 的 program id 才能进入链上验证"

→ 5 verified pids 全部进入 Stage E 链上验证。
→ Lifinity **不**进入 Stage E (无 source)。

> "多个 program id 候选时必须全部保留，并标记 primary/secondary"

→ Raydium CLMM/CPMM 各自保留 mainnet (primary) + devnet (secondary) 两个 candidates；Stage E 只对 primary 跑 on-chain verify (devnet 标 "do not use")。

> "对 SDK 中 program id 和 docs 中 program id 不一致的情况，必须标记 conflict"

→ 5 协议均无 SDK/docs 冲突 (single source each)。

## 3. 关键修正

- **Raydium CLMM**: 用 raydium-clmm 仓库 `lib.rs` 中 `declare_id!` 宏（Level A; mainnet 编译标志下）；**不**用 SDK example 或 memory
- **Raydium CPMM**: 同上
- **Meteora DLMM**: 用 docs.meteora.ag (Level A; official domain)
- **Orca Whirlpools**: 用 github.com/orca-so/whirlpools README (Level A; official org/repo)

## 4. 不在本阶段做

- ❌ 不跑 on-chain verify (Stage E 才做)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不跑 GPA (Stage F)
- ❌ 不调 SDK / indexer / API

## 5. 安全断言

```text
oficial_source_verified         = 5/6
unknown                          = 1/6 (Lifinity; per spec)
this_stage_did_not_hard_code     = true
this_stage_did_not_load_keypair  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 6. 下一阶段

Stage E: 链上只读 program verification v2 — 对 5 verified pids 跑 getAccountInfo。
