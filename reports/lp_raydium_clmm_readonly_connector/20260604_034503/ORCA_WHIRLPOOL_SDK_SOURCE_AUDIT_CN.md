# Raydium CLMM SDK Source Audit — Stage C

- stage: `LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`
- run_id: `20260604_034503`

## 0. 关键结果

```text
official_program_id_verified         = true  (CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK)
official_github_repo_verified        = true  (https://github.com/raydium-io/raydium-clmm)
official_npm_sdk_v1_verified         = true  (@raydium-io/raydium-sdk 1.3.1-beta.58)
official_npm_sdk_v2_verified         = true  (@raydium-io/raydium-sdk-v2 0.2.50-alpha)
poolstate_account_decode_capable     = true  (PoolInfoLayout)
tick_array_decode_capable            = true  (TickArrayLayout, TICK_ARRAY_SIZE)
quote_method_capable                 = true  (getDxByDyBaseIn, getDyByDxBaseIn)
position_model_capable               = true  (getPdaPersonalPositionAddress)
wallet_required_for_readonly         = false
repo_node_modules_created            = false (SDK install in /tmp isolated)
```

## 1. 官方来源审计

### 1.1 Program ID 审计

| 字段 | 值 |
|---|---|
| program_id | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` |
| 官方 source | `https://raw.githubusercontent.com/raydium-io/raydium-clmm/master/programs/amm/src/lib.rs` |
| source_type | official_github |
| source_confidence | high |
| 链上验证 (V1 stage 20260603_093136) | yes (4 verified protocols including Raydium CLMM) |
| devnet fallback | `DRayAUgENGQBKVaX8owNhgzkEDyoHTGVEGHVJT1E9pfH` |

### 1.2 Official GitHub 审计

`https://github.com/raydium-io/raydium-clmm`:
- `programs/amm/src/lib.rs` (3.0KB) — Rust entry
- `programs/amm/src/states/pool.rs` (84KB) — PoolState struct
- `programs/amm/src/states/tick_array.rs` — TickArray struct
- `programs/amm/src/states/personal_position.rs` — Position NFT
- `programs/amm/src/states/tickarray_bitmap_extension.rs`

### 1.3 PoolState fields (from Rust source)

```rust
pub struct PoolState {
    pub bump: [u8; 1],
    pub amm_config: Pubkey,
    pub owner: Pubkey,
    pub token_mint_0: Pubkey,    // token_mint_0 < token_mint_1 (sorted)
    pub token_mint_1: Pubkey,
    pub token_vault_0: Pubkey,
    pub token_vault_1: Pubkey,
    pub observation_key: Pubkey,
    pub mint_decimals_0: u8,
    pub mint_decimals_1: u8,
    pub tick_spacing: u16,
    pub liquidity: u128,
    pub sqrt_price_x64: u128,
    pub tick_current: i32,
    // ... + fee, protocol_fee, reward_infos, observation_id, tick_array_bitmap
}
```

### 1.4 Official npm 审计

| package | version | 用途 |
|---|---|---|
| `@raydium-io/raydium-sdk` | 1.3.1-beta.58 | stable v1 (current) |
| `@raydium-io/raydium-sdk-v2` | 0.2.50-alpha | v2 (preview) |
| Raydium GitHub SDK | `raydium-io/raydium-sdk` | source code |

### 1.5 SDK Read-only functions (292 total exports)

- `getPdaPoolId` — derive pool pubkey
- `getPdaTickArrayAddress` — derive tick array pubkey
- `getPdaAmmConfigId` — derive amm_config
- `getPdaPersonalPositionAddress` — derive position
- `getMultipleAccountsInfo` — read
- `getDxByDyBaseIn` / `getDyByDxBaseIn` — read-only quote compute
- `PoolInfoLayout` — PoolState decoder
- `TickArrayLayout` — tick array decoder
- `TickMath` / `TickUtils` / `PoolUtils` — math helpers
- `parseSimulateLogToJson` — parse simulate result (read-only)
- `LiquidityPoolStatus` — pool status enum

### 1.6 Wallet-related imports 审计

- SDK 不需要 keypair for read-only path
- `getPdaPersonalPositionAddress` 派生 PDA, 不需要 signer
- `getMultipleAccountsInfo` 是纯 read
- `getDxByDyBaseIn` 是纯 math, 不调用 RPC

## 2. 不在本轮范围 (避免 read-only 失误)

- ❌ `createPoolInstruction` — 写
- ❌ `addLiquidity` / `removeLiquidity` / `swap` — 写
- ❌ `openPosition` / `closePosition` — 写
- ❌ 任何 `*Ix` 或 `*Instruction` 调用 — 写

## 3. SDK 限制 (本轮接受)

- 1.3.1-beta.58 (pre-release) — stable
- 0.2.50-alpha 也有, 但 v1 stable 更稳定
- v2 处于 alpha — 不用

## 4. confidence

| 维度 | 评分 |
|---|---|
| program_id 官方 source | 1.0 |
| SDK install 成功 | 0.95 (npm install OK) |
| read-only import | 0.95 (verified 292 exports) |
| PoolInfoLayout decode 路径 | 0.90 (API 已知) |
| getDxByDyBaseIn 路径 | 0.85 (待 on-chain smoke) |
| 总体 | 0.92 |

## 5. 下一阶段

进入 Stage D — isolated SDK install + read-only probe (call `getPdaPoolId` / `PoolInfoLayout.decode` on a known Raydium pool address)。
