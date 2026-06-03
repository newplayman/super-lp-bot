# Solana Program ID On-Chain Verification v2 — Stage E

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 关键结果

```text
verified_count  = 4/5
skipped_count  = 1 (Lifinity)
not_found_count = 1 (Raydium CPMM)
```

## 1. 5 verified pids + 1 not found

| protocol | program_id | on-chain status | executable | owner | data_len |
|---|---|---|---|---|---|
| Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | **verified** | ✅ | BPFLoaderUpgradeab1e... | 48 |
| Meteora DAMM v2 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | **verified** | ✅ | BPFLoaderUpgradeab1e... | 48 |
| Orca Whirlpools | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | **verified** | ✅ | BPFLoaderUpgradeab1e... | 36 |
| Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | **verified** | ✅ | BPFLoaderUpgradeab1e... | 48 |
| Raydium CPMM | `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` | **not_found** | ❌ (account null) | (n/a) | 0 |
| Lifinity | (unknown) | **skipped_unknown** (per spec) | n/a | n/a | n/a |

## 2. Raydium CPMM 详细分析

**`declare_id!("CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C")`** 在 `raydium-cp-swap` 仓库 `lib.rs` 中显式声明 (mainnet 编译路径)。

但 on-chain `getAccountInfo` on both public RPCs (api.mainnet-beta.solana.com, solana.publicnode.com) 返回 `value: null` (多次 retry; commitment=confirmed) → 4 个 on-chain query 中**无**返回。

可能原因：
1. 该 program 尚未在 mainnet deploy（最新 cp-swap 仓库；可能仅 devnet）
2. mainnet 上的实际 AMM v4 CPMM 在 `raydium-amm-v3` 仓库，但 `declare_id!` 不同（CPAMdpZ... 在搜索结果中未匹配）
3. RPC cache 错乱（unlikely，已 retry）

**当前结论**：`CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` 在 mainnet 不可验证。

**修复**（下一轮 fix_repeat）：重新拉 mainnet-deployed CPMM 的 program id，可能从 `raydium-amm-v3` 仓库源或 Raydium 官方 docs。

## 3. on-chain verified 程序特征

- **owner 全部是 BPFLoaderUpgradeab1e...** — 4 个 verified 都是 upgradeable loader
- **data_len 都是 36 或 48 字节** — 符合 binary (`.so`) 程序的 programdata 头
- **executable=true** — 全部是 executable
- **lamports 0** (账户自身 0 lamports; rent 由 programdata 持有)

## 4. 不在本阶段做

- ❌ 不跑 GPA (Stage F)
- ❌ 不调 SDK / indexer / API
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不修改任何 program id (即使 Raydium CPMM on-chain 不可验证; 我们**不**改 pid)

## 5. 安全断言

```text
this_stage_only_onchain_verify    = true
this_stage_did_not_sign            = true
this_stage_did_not_send_tx         = true
this_stage_did_not_load_keypair   = true
solana_wallet_or_keypair_touched  = false
can_run_probe_now                 = false
v2_line_count_unchanged           = true (992)
```

## 6. 下一阶段

Stage F: bounded GPA smoke v2 — 仅对 4 verified pids 跑 getProgramAccounts (dataSlice 0 bytes, 8s timeout)。
