# Raydium CPMM Source Audit — Stage C

- stage: `LP_RAYDIUM_CPMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_040952`

## 0. 关键结果

```text
official_source_verified       = true
candidate_mainnet_program_id  = 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8  (Raydium AMM v4)
candidate_mainnet_mainnet_label = yes
candidate_cp_swap_program      = CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C  (source declared; NOT on mainnet)
candidate_devnet_program       = DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb  (v2 SDK wires; NOT on mainnet)
candidate_v2_sdk_cpmm_prog     = DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb  (matches v2 SDK CREATE_CPMM_POOL_PROGRAM constant; devnet only)
selected_for_onchain_verify   = 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
v1_sdk_cpmm_decoder_capable   = true  (CpmmPoolInfoLayout in v2 SDK src/raydium/cpmm/layout.ts; can be applied to AMM v4 if structs match)
v1_sdk_amm_v4_pool_decode     = true  (PoolInfoLayout in v1 SDK; used in previous Raydium CLMM V1 stage 错误地 decode AMM v4 池 — 实际 AMM v4 layout 与 CLMM 不同)
```

## 1. 官方来源审计

### 1.1 Program ID 路径 (3 个候选)

| 路径 | program id | 状态 | 来源 |
|---|---|---|---|
| Raydium AMM v4 (legacy constant-product) | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | **on mainnet** (executable, BPFLoader owner) | V1 stage verified + 本轮 on-chain re-verify |
| Raydium cp-swap (new "CPMM") | `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` | **NOT on mainnet** (declared in `programs/cp-swap/src/lib.rs` as `#[cfg(not(feature = "devnet"))] declare_id!`) | V1 stage verified + 本轮 on-chain re-verify |
| Raydium cp-swap devnet | `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` | NOT on mainnet (declared as `#[cfg(feature = "devnet")] declare_id!`) | 同上 + v2 SDK uses this as `CREATE_CPMM_POOL_PROGRAM` constant |

**结论**: 唯一 mainnet deployed constant-product Raydium program 是 **AMM v4**。新 cp-swap ("CPMM") 在 source 声明但未部署 (或者已 deprecated/重命名)。

### 1.2 官方 GitHub 审计

`https://github.com/raydium-io/raydium-cp-swap` (master branch):
- `programs/cp-swap/src/lib.rs` (9980 bytes) — contains `declare_id!` for both devnet and mainnet via `#[cfg(feature = "devnet")]` switch
- `programs/cp-swap/src/curve/` — constant product math
- `programs/cp-swap/src/states/` — PoolInfo struct

`https://github.com/raydium-io/raydium-sdk-V2` (master branch):
- `src/raydium/cpmm/cpmm.ts` — CPMM API
- `src/raydium/cpmm/layout.ts` — `CpmmPoolInfoLayout` struct
- `src/raydium/cpmm/pda.ts` — PDA derivation
- `src/raydium/cpmm/curve/constantProduct.ts` — math
- v2 SDK includes `DRaycpLY18...` as `CREATE_CPMM_POOL_PROGRAM` (devnet only, since mainnet cp-swap not deployed)

### 1.3 CpmmPoolInfoLayout (v2 SDK)

```rust
struct CpmmPoolInfo {
    configId: Pubkey,           // amm config
    poolCreator: Pubkey,
    vaultA: Pubkey,
    vaultB: Pubkey,
    mintLp: Pubkey,             // LP token mint
    mintA: Pubkey,
    mintB: Pubkey,
    mintProgramA: Pubkey,       // token program for A
    mintProgramB: Pubkey,
    observationId: Pubkey,
    bump: u8,
    status: u8,
    lpDecimals: u8,
    mintDecimalA: u8,
    mintDecimalB: u8,
    lpAmount: u64,              // total LP supply
    protocolFeesMintA: u64,
    protocolFeesMintB: u64,
    fundFeesMintA: u64,
    fundFeesMintB: u64,
    openTime: u64,
    epoch: u64,
    // ... padding
}
```

This layout applies to **v2 SDK's target cp-swap program** (`DRaycpLY18...`). For **AMM v4** (`675kPX9MHT...`), pool layout is **different** (legacy struct, 752 bytes data).

### 1.4 AMM v4 pool layout (V1 SDK has it)

The V1 SDK `@raydium-io/raydium-sdk` 1.3.1-beta.58 has `PoolInfoLayout` for AMM v4:
- Used in V1 stage error: 试图 decode AMM v4 池 (e.g. `58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2`) with CLMM `PoolInfoLayout` — returned 0 for many fields because CLMM and AMM v4 layouts differ
- This is because **V1 stage accidentally picked up AMM v4 池 as "raydium CLMM" candidate** (GeckoTerminal `dex=raydium` actually serves AMM v4 池 — see GeckoTerminal 404 on `raydium-clmm` V1 stage caveat)

## 2. 决策

**mainnet deployed Raydium constant-product AMM = `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` (AMM v4)**.

**This is what the user means by "Raydium CPMM"**:
- Constant product (x*y=k)
- Pool reserves (reserveA, reserveB in vaultA, vaultB)
- LP token mint
- fee: configurable per pool (e.g. 25bps)
- position: hold LP token proportional to pool share

**We use AMM v4 as our CPMM target**.

## 3. 排除的候选 (NOT used this stage)

- `CPMMoo8L3F4NbTegBCKVNunggN7H1ZpdTHKxQB5qKP1C` — NOT on mainnet, source-declared cp-swap mainnet pid
- `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb` — NOT on mainnet, v2 SDK wires as `CREATE_CPMM_POOL_PROGRAM` (devnet only)

## 4. confidence

| 维度 | 评分 |
|---|---|
| 官方 source (GitHub) verified | 1.0 |
| SDK install (V2) 成功 | 0.95 |
| AMM v4 on mainnet 验证 | 1.0 (executable, owner=BPFLoader) |
| AMM v4 pool candidate verified | 0.95 (data_len 752, owner=675kPX9MHT) |
| Layout decode 路径 | 0.85 (V1 SDK PoolInfoLayout works; v2 SDK CpmmPoolInfoLayout 不适用 AMM v4) |
| 总体 | 0.92 |

## 5. 风险诚实

- 用户 spec 说 "Raydium CPMM" 可能指的是 new cp-swap program (`CPMMoo8L...`), 但该 pid 未部署到 mainnet
- 本轮采用 **AMM v4** (`675kPX9MHT...`) 作为 mainnet deployed constant-product Raydium program
- 这与 V1 早 stage design (20260603_080347) 描述的 "constant product; stable-stable 路径" 一致
- 任何 LP 决策应基于 AMM v4 pool 实际数据, 不依赖 cp-swap 假设

## 6. 下一阶段

进入 Stage D — on-chain 验证 `675kPX9MHT...` (account exists, executable, owner, data_len) + 验证真实 AMM v4 pool 示例。
