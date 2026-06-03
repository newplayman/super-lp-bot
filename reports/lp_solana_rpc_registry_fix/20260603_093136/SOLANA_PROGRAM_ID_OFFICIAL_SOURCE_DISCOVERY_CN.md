# Solana Program ID Official Source Discovery — Stage C

- stage: `LP_SOLANA_RPC_REGISTRY_FIX_REPEAT_V1`
- run_id: `20260603_093136`

## 0. 摘要

| protocol | official source | program id | source_type | source_confidence | verified |
|---|---|---|---|---|---|
| **Meteora DLMM** | docs.meteora.ag/core-products/dlmm | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | oficial_docs | **high** | yes |
| **Meteora DAMM v2** | github.com/MeteoraAg/damm-v2-sdk | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | oficial_github | **high** | yes |
| **Orca Whirlpools** | github.com/orca-so/whirlpools (README.md) | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | oficial_github | **high** | yes |
| **Raydium CLMM** | github.com/raydium-io/raydium-clmm (lib.rs declare_id!) | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | oficial_github | **high** | yes |
| **Raydium CPMM** | github.com/raydium-io/raydium-cp-swap (lib.rs declare_id!) | `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` | oficial_github | **high** | yes |
| **Lifinity** | docs.lifinity.io 404; no public GitHub source found | **unknown** | unknown | n/a | no |

## 1. 6 协议详细来源

### 1.1 Meteora DLMM (P0)

- **oficial_source_url**: `https://docs.meteora.ag/core-products/dlmm`
- **source_type**: `oficial_docs` (Level A)
- **program_id_candidates**:
  - `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` ← **primary** (extracted from official docs page)
- **evidence_excerpt_short**: docs.meteora.ag/core-products/dlmm page returned the program id directly
- **source_fetch_success**: yes
- **source_confidence**: high (Level A; oficial domain; 单一来源)
- **invalid_reason**: (none)

### 1.2 Meteora DAMM v2 (P1)

- **oficial_source_url**: `https://github.com/MeteoraAg/damm-v2-sdk`
- **source_type**: `oficial_github` (Level A)
- **program_id_candidates**:
  - `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` ← **primary** (README)
- **evidence_excerpt_short**: damm-v2-sdk README returned the program id
- **source_fetch_success**: yes
- **source_confidence**: high
- **invalid_reason**: (none)

### 1.3 Orca Whirlpools (P1)

- **oficial_source_url**: `https://github.com/orca-so/whirlpools` (README.md)
- **source_type**: `oficial_github` (Level A)
- **program_id_candidates**:
  - `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` ← **primary** (README)
- **evidence_excerpt_short**: orca-so/whirlpools README returned the program id
- **source_fetch_success**: yes
- **source_confidence**: high
- **invalid_reason**: (none)

### 1.4 Raydium CLMM (P2)

- **oficial_source_url**: `https://raw.githubusercontent.com/raydium-io/raydium-clmm/master/programs/amm/src/lib.rs`
- **source_type**: `oficial_github` (Level A; `declare_id!` macro in mainnet build)
- **program_id_candidates**:
  - `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` ← **primary** (mainnet `declare_id!`)
  - `DRayAUgENGQBKVaX8owNhgzkEDyoHTGVEGHVJT1E9pfH` (devnet, **NOT** used)
- **evidence_excerpt_short**: `#[cfg(not(feature = "devnet"))] declare_id!("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK");`
- **source_fetch_success**: yes
- **source_confidence**: high (Level A; 源代码中显式 `declare_id!`; mainnet 与 devnet 通过 cfg flag 区分)
- **invalid_reason**: (none)

### 1.5 Raydium CPMM (P2)

- **oficial_source_url**: `https://raw.githubusercontent.com/raydium-io/raydium-cp-swap/master/programs/cp-swap/src/lib.rs`
- **source_type**: `oficial_github` (Level A; `declare_id!` macro in mainnet build)
- **program_id_candidates**:
  - `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` ← **primary** (mainnet)
  - `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` (devnet, **NOT** used)
- **evidence_excerpt_short**: `#[cfg(not(feature = "devnet"))] declare_id!("CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C");`
- **source_fetch_success**: yes
- **source_confidence**: high
- **invalid_reason**: (none)

### 1.6 Lifinity (P2)

- **oficial_source_url**: docs.lifinity.io → 404
- **source_type**: `unknown`
- **program_id_candidates**: []
- **evidence_excerpt_short**: docs.lifinity.io (canonical docs URL) returns 404; no public GitHub source found in this round
- **source_fetch_success**: no
- **source_confidence**: unknown
- **invalid_reason**: docs.lifinity.io returns 404; we will not hard-code from memory; spec forbids blog/forum/unofficial source

## 2. 5/6 verified (high confidence); 1/6 (Lifinity) unknown

**Verified count: 5** (DLMM, DAMM v2, Orca, Raydium CLMM, Raydium CPMM)
**Unverified count: 1** (Lifinity)

Lifinity 维持 `unknown` per spec:
- spec 禁止凭模型记忆硬编码
- spec 禁止从 blog / Twitter / 论坛 / 推测获取来源
- Lifinity 公开资料稀少；docs.lifinity.io 404
- 任何"Lifinity 似乎是 X base58"的回复都是 hallucination，不能接受

## 3. 与上游 stage 的差异

| protocol | upstream (last stage) | this stage |
|---|---|---|
| Meteora DLMM | unknown → oficial_doc_required | **LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo** (verified) |
| Meteora DAMM v2 | unknown → oficial_doc_required | **cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG** (verified) |
| Orca Whirlpools | unknown → oficial_doc_required | **whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc** (verified) |
| Raydium CLMM | unknown → oficial_doc_required | **CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK** (verified, from declare_id! macro in source) |
| Raydium CPMM | unknown → oficial_doc_required | **CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C** (verified, from declare_id! macro in source) |
| Lifinity | unknown → sdk_required | **unknown** (no public source found) |

## 4. 关键修正 (相对于任何 memory-only 来源)

- Meteora DLMM: 用 `docs.meteora.ag/core-products/dlmm` 而**非** SDK or memory
- Orca Whirlpools: 用 `github.com/orca-so/whirlpools/README.md` 而**非** memory
- Raydium CLMM: 用 `lib.rs` 中 `declare_id!("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK")` 而**非** SDK example
- Raydium CPMM: 同上
- Meteora DAMM v2: 用 `damm-v2-sdk` README 而**非** memory

## 5. 不在本阶段做

- ❌ 不 webfetch 任何非官方来源 (blog / Twitter / 论坛)
- ❌ 不从模型记忆硬编码任何 program id
- ❌ 不跑链上验证 (Stage E 才做)
- ❌ 不接 wallet / 不读 keypair / 不签名
- ❌ 不调 swap / open LP / close LP / collect fee / bridge
- ❌ 不构造 transaction

## 6. 安全断言

```text
this_stage_only_source_discovery    = true
this_stage_did_not_hard_code       = true  (5/6 from official; 1/6 stays unknown)
this_stage_did_not_run_onchain      = true  (Stage E)
this_stage_did_not_load_keypair    = true
solana_wallet_or_keypair_touched   = false
can_run_probe_now                  = false
```

## 7. 下一阶段

进入 Stage D (program id registry v2)：5 verified program id 写入 registry；Lifinity 仍标 unknown。
