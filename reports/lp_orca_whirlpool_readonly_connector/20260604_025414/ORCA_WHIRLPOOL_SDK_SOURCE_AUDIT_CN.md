# Orca Whirlpool SDK Source Audit — Stage C

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
official_program_id_verified        = true  (whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc)
official_github_repo_verified       = true  (https://github.com/orca-so/whirlpools)
official_npm_sdk_verified           = true  (@orca-so/whirlpools 8.0.0)
official_npm_sdk_legacy_verified    = true  (@orca-so/whirlpools-sdk 0.20.0)
whirlpool_account_decode_capable    = true  (fetchConcentratedLiquidityPool, fetchWhirlpoolsByTokenPair)
tick_array_decode_capable           = true  (fetchTickArrayOrDefault internal)
quote_method_capable                = true  (getSwapQuote<T>)
position_model_capable              = true  (fetchPositionsForOwner, fetchPositionsInWhirlpool)
wallet_required_for_readonly        = false (setRpc + address only)
repo_node_modules_created           = false (SDK install in /tmp isolated)
```

## 1. 官方来源审计

### 1.1 Program ID 审计

| 字段 | 值 |
|---|---|
| program_id | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` |
| 官方 source | `https://github.com/orca-so/whirlpools` (Anchor.toml declare_id) |
| source_type | official_github |
| source_confidence | high |
| 链上验证 (V1 stage 20260603_093136) | yes (4 verified protocols including Orca) |

### 1.2 Official GitHub 审计

`https://github.com/orca-so/whirlpools`:
- `programs/whirlpool/src/lib.rs` (62KB) — Rust on-chain program
- `idl/` (artifact dir, see docs) — IDL via Codama generation
- `ts-sdk/whirlpool/` — TypeScript SDK (current)
- `ts-sdk/whirlpool/src/pool.ts` — `fetchConcentratedLiquidityPool`, `fetchSplashPool`, `fetchWhirlpoolsByTokenPair`
- `ts-sdk/whirlpool/src/swap.ts` — `getSwapQuote<T>` (read-only), `swapInstructions<T>`, `swap<T>` (write)
- `ts-sdk/whirlpool/src/position.ts` — `fetchPositionsForOwner`, `fetchPositionsInWhirlpool`
- `ts-sdk/whirlpool/src/token.ts` — token helpers
- `ts-sdk/whirlpool/src/config.ts` — `setRpc`, no Keypair required for read-only

### 1.3 Official npm 审计

| package | version | 用途 |
|---|---|---|
| `@orca-so/whirlpools` | 8.0.0 | current (deprecates 0.x) |
| `@orca-so/whirlpools-sdk` | 0.20.0 | legacy (still maintained) |
| `@orca-so/whirlpools-core` | 7.0.0 | core types |
| `@orca-so/whirlpools-client` | 7.0.0 | client primitives |
| `@orca-so/tx-sender` | 3.0.0 | transaction sender (write path) |
| `@solana-program/{memo,system,token,token-2022}` | ^0.10 | Solana program clients |

### 1.4 Read-only capability 验证

通过 `require('@orca-so/whirlpools')` 加载 42 个 export function:
- `fetchConcentratedLiquidityPool(rpc, address)` — 读 single whirlpool
- `fetchSplashPool(rpc, address)` — 读 splash pool (legacy)
- `fetchWhirlpoolsByTokenPair(rpc, mintA, mintB)` — 按 token pair 查
- `getSwapQuote<T>` (内部) — read-only quote
- `fetchPositionsForOwner(rpc, ownerAddress)` — read positions
- `fetchPositionsInWhirlpool(rpc, whirlpoolAddress)` — read positions in pool
- `getPayer`, `getRpcConfig` — config helpers
- `setDefaultSlippageToleranceBps` — config only

### 1.5 Wallet-related imports 审计

`config.ts` imports `KeyPairSigner`, `TransactionSigner` (types) — 但 read-only 路径不要求 keypair。
`swap.ts` 和 `position.ts` 注释中提到 `loadWallet()` — 是 high-level helper (写路径); `getSwapQuote` 是 read-only 不需要。
`token.ts` 提到 `generateKeyPairSigner` — 也是写路径。

**read-only 路径**:
- `fetch*` 全部 read
- `getSwapQuote` 是内部 helper, public 通过 `swapInstructions` 的 quote-only 模式
- 不需要 signer / Keypair

## 2. 不在本轮范围 (避免 read-only 失误)

- ❌ `swap<T>()` — 写路径
- ❌ `swapInstructions<T>()` — 构造 instructions (可用于 simulateTransaction 但本轮不做)
- ❌ `decreaseLiquidity`, `increaseLiquidity`, `harvest`, `lockPosition`, `resetPositionRange` — 写路径
- ❌ `createPool` — 写路径
- ❌ `loadWallet` — 写路径 helper
- ❌ `setRpc` 改变全局 RPC — 用 local RPC 即可

## 3. SDK 限制 (本轮接受)

- IDL 是 CI artifact, 不在 repo source — 但 @orca-so/whirlpools 8.0.0 内置 IDL
- `getSwapQuote` 是 internal — 通过 `swapInstructions` 的 quote-only 模式访问

## 4. confidence

| 维度 | 评分 |
|---|---|
| program_id 官方 source | 1.0 |
| SDK install 成功 | 0.95 (npm install OK) |
| read-only import | 0.95 (verified 42 exports) |
| fetchConcentratedLiquidityPool 路径 | 0.90 (API 已知, 需 on-chain smoke) |
| getSwapQuote 路径 | 0.85 (internal helper, 需 probe) |
| 总体 | 0.92 |

## 5. 下一阶段

进入 Stage D — isolated SDK install verification + read-only probe (call `fetchConcentratedLiquidityPool` on a known Orca pool address from upstream).
