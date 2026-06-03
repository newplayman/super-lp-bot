# Solana P1/P2 Registry Readiness v2 — Stage H

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 5 协议 readiness v2 详细

### P1 - Meteora DAMM v2

- **oficialmente_sourced**: ✅ (`cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` from damm-v2-sdk README)
- **verified_onchain**: ✅ (executable=true; BPFLoaderUpgradeable; data_len=48)
- **gpa_feasible**: ❌ (timeout 8.1s on public RPC)
- **sdk_or_api_path_available**: partial (Meteora SDK shared with DLMM; covers both)
- **connector_priority_after_fix**: P1_backup (lower than Meteora DLMM; DLMM 是 bin-based 范式创新，DAMM v2 是 constant product)
- **blocker**: GPA fails on public RPC; SDK shared with DLMM (only one connector needs to wire Meteora SDK; both DLMM + DAMM v2 use it)
- **ready_for_connector**: false

### P1 - Orca Whirlpools

- **oficialmente_sourced**: ✅ (`whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` from orca-so/whirlpools README)
- **verified_onchain**: ✅ (executable=true; BPFLoaderUpgradeable; data_len=36)
- **gpa_feasible**: ❌ (json-rpc error -32010; "program too large" for getProgramAccounts)
- **sdk_or_api_path_available**: partial (Orca SDK TypeScript `@orca-so/whirlpools-sdk`; mature; IDL public)
- **connector_priority_after_fix**: P1 (tied with Meteora DLMM; Orca SDK is mature; tick array model is V3-like and well-understood)
- **blocker**: GPA fails with -32010; Orca SDK exists but not wired
- **ready_for_connector**: false

### P2 - Raydium CLMM

- **oficialmente_sourced**: ✅ (`CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` from raydium-clmm `lib.rs` declare_id!)
- **verified_onchain**: ✅ (executable=true; BPFLoaderUpgradeable; data_len=48)
- **gpa_feasible**: ❌ (HTTP 429 rate-limited on public RPC)
- **sdk_or_api_path_available**: partial (Raydium SDK TypeScript; @raydium-io/raydium-sdk; Raydium API)
- **connector_priority_after_fix**: P2 (by spec; lower than Meteora/Orca; high quality but P2 priority)
- **blocker**: GPA rate-limited on public RPC; Raydium SDK exists but not wired
- **ready_for_connector**: false

### P2 - Raydium CPMM

- **oficially_sourced**: ✅ (from raydium-cp-swap `lib.rs` declare_id!: `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C`)
- **verified_onchain**: ❌ (**program not found on mainnet**; both public RPCs return null; pid from declare_id! is not yet deployed on mainnet)
- **gpa_feasible**: n/a (skipped per spec; pid not on chain)
- **sdk_or_api_path_available**: partial (Raydium SDK shared with CLMM)
- **connector_priority_after_fix**: P2_low (CPMM is constant product; lower fee; less interesting for LP research; even if verified, low priority)
- **blocker**: 
  - `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` not on mainnet (multiple RPCs; multiple retries; both null)
  - 推测：cp-swap 是 new repo; pid 在 mainnet 尚未 deploy
  - actual mainnet CPMM (AMM v4) 可能在 `raydium-amm-v3` 仓库 (lib.rs 中有 `declare_id!`)
  - **fix_repeat 阶段需重新拉** raydium-amm-v3 or official docs
- **ready_for_connector**: false

### P2 - Lifinity

- **oficially_sourced**: ❌ (no public source found; docs.lifinity.io 404; no GitHub source)
- **verified_onchain**: n/a (no pid)
- **gpa_feasible**: n/a
- **sdk_or_api_path_available**: limited (Lifinity SDK public material sparse)
- **connector_priority_after_fix**: P2_deferred
- **blocker**: docs.lifinity.io returns 404; spec forbids memory hardcode
- **ready_for_connector**: false

## 1. 5 协议 readiness 汇总

| protocol | priority | source | verify | GPA | sdk/api | ready |
|---|---|---|---|---|---|---|
| Meteora DLMM | P0 | ✅ | ✅ | ❌ | partial | ⚠️ |
| Meteora DAMM v2 | P1 | ✅ | ✅ | ❌ | partial (Meteora SDK shared) | ❌ |
| Orca Whirlpools | P1 | ✅ | ✅ | ❌ (program too large) | partial | ❌ |
| Raydium CLMM | P2 | ✅ | ✅ | ❌ (rate limit) | partial | ❌ |
| Raydium CPMM | P2 | ✅ | **❌ (not on mainnet)** | n/a | partial | ❌ |
| Lifinity | P2 | ❌ | n/a | n/a | limited | ❌ |

**5/6 protocols have officially sourced program id**; **4/6 verified on chain**; **0/6 GPA feasible on public RPC**; **0/6 ready for connector** (因为 GPA 障碍).

## 2. 共同 blocker

**GPA on public RPC 不适用于任何主流量级 AMM 池** (3 个 AMM 程序都太大 / 太多 accounts; public RPC 限 5MB response, 不可 unbounded):

- 解决需要:
  - **paid RPC** (Helius / Triton / QuickNode) with higher rate limit and larger response
  - **indexer / API** (Meteora DLMM API, Raydium API, etc.) 直接 list 池 without GPA
  - **sub-second** GPA with dataSlice + memcmp filter (program-specific offsets)

## 3. 下一阶段含义

- 0/6 protocols ready for connector → 不能进任何 connector stage
- **Meteora DLMM** 4/5 sub-conditions verified (only GPA blocks) → 最接近 ready
- **Raydium CPMM** 仍有 on-chain 障碍 (pid not on mainnet) → **需 fix_repeat 再修一次** (用 raydium-amm-v3 or docs)
- **Lifinity** 维持 unknown → 不进任何 connector

## 4. 不在本阶段做

- ❌ 不 webfetch 任何官方 source
- ❌ 不跑 on-chain verify (Stage E)
- ❌ 不跑 GPA (Stage F)
- ❌ 不调 SDK / indexer / API
- ❌ 不接 wallet / 不读 keypair

## 5. 安全断言

```text
P1_Meteora_DAMM_v2_ready       = false
P1_Orca_Whirlpools_ready       = false
P2_Raydium_CLMM_ready          = false
P2_Raydium_CPMM_ready          = false  (pid not on mainnet)
P2_Lifinity_ready              = false
this_stage_did_not_hard_code    = true
this_stage_did_not_load_keypair = true
solana_wallet_or_keypair_touched = false
can_run_probe_now               = false
```
