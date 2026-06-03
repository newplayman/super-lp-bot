# Meteora DLMM SDK Package Audit — Stage C

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`

## 0. 关键结果

```text
package_name             = @meteora-ag/dlmm
resolved_version         = 1.9.10
install_attempted        = true
install_success          = true
install_dir              = /tmp/lpbot_meteora_dlmm_sdk_probe_20260603_130532/node_modules/@meteora-ag/dlmm
has_dlmm_create          = true (DLMM class static method, takes connection + PublicKey)
has_get_active_bin       = true (dlmmPool.getActiveBin(): Promise<BinLiquidity>)
has_swap_quote           = true (dlmmPool.swapQuote(inAmount, swapForY, allowedSlippage, binArrays, isPartialFill, maxExtraBinArrays): SwapQuote)
has_get_fee_info         = true (dlmmPool.getFeeInfo(): FeeInfo)
has_bin_array_helpers    = true (getBinArrayForSwap, getBinArrays, getBinArrayAroundActiveBin, getBinArrayIndexesCoverage, getBinArrayKeysCoverage)
wallet_related_imports_present   = true (Keypair imported from @solana/web3.js; but ONLY used by position-creation methods)
wallet_related_imports_used      = false (we will NOT call position-creation methods)
read_only_methods_available      = true (DLMM.create + getActiveBin + getFeeInfo + getLbPairLockInfo + getTokensMintFromPoolAddress + getTokenDecimals + getBinArrayForSwap + swapQuote)
l-b-c-l-m-m_program_ids_mainnet  = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"  (matches V1 verified)
confidence               = 0.95
```

## 1. npm metadata

```bash
$ npm view @meteora-ag/dlmm version
1.9.10

$ npm view @meteora-ag/dlmm dist-tags
{ next: '1.9.5-rc.4', beta: '1.9.8-rc.0', latest: '1.9.10' }

$ npm view @meteora-ag/dlmm repository
{ type: 'git', url: 'git+https://github.com/MeteoraAg/dlmm-sdk.git', directory: 'ts-client' }
```

## 2. Install 详情 (isolated, repo root 不污染)

| 项 | 值 |
|---|---|
| install_dir | `/tmp/lpbot_meteora_dlmm_sdk_probe_20260603_130532/` |
| packages installed | 152 (1 direct + 151 transitive) |
| install_time | ~4 min (cold cache) |
| audit_warnings | 11 (7 moderate, 4 high) — not blocking, not in our read-only code path |
| repo root touched | **NO** (npm install 在 /tmp; repo root 完全不动) |
| repo `node_modules/` | **NOT created** (没污染 repo) |

## 3. SDK API surface (from dist/index.d.ts)

### 3.1 DLMM class methods (used in our read-only smoke)

| method | signature | read-only? |
|---|---|---|
| `DLMM.create` | `(connection: Connection, dlmm: PublicKey, opt?: Opt): Promise<DLMM>` | **YES** |
| `dlmmPool.getActiveBin` | `(): Promise<BinLiquidity>` | **YES** |
| `dlmmPool.getFeeInfo` | `(): FeeInfo` | **YES** |
| `dlmmPool.getLbPairLockInfo` | `(): Promise<PairLockInfo>` | **YES** |
| `dlmmPool.getBinArrayForSwap` | `(swapForY: boolean, count?: number): Promise<BinArrayAccount[]>` | **YES** |
| `dlmmPool.getBinArrays` | `(): Promise<BinArrayAccount[]>` | **YES** (private; called internally) |
| `dlmmPool.swapQuote` | `(inAmount, swapForY, allowedSlippage, binArrays, isPartialFill, maxExtraBinArrays): SwapQuote` | **YES** (本地计算; 不构造 tx) |
| `dlmmPool.swapQuoteExactOut` | similar to swapQuote | **YES** |
| `DLMM.getLbPairs` (static) | `(connection, opt?): Promise<LbPairAccount[]>` | YES (uses GPA; not in our read-only path) |

### 3.2 Helpers (in SDK exports)

| helper | signature | usage in smoke |
|---|---|---|
| `getTokensMintFromPoolAddress` | `(connection, poolAddress, opt?): Promise<{tokenXMint, tokenYMint}>` | resolve mints from pool |
| `getTokenDecimals` | `(conn, mint): Promise<number>` | get SPL decimals |
| `getTokenBalance` | `(conn, tokenAccount): Promise<bigint>` | optional reserve query |
| `LBCLMM_PROGRAM_IDS` | `{ devnet, localhost, "mainnet-beta" }` | mainnet pid = `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` (V1 verified) |

### 3.3 Position-creation methods (NOT used; wallet/keypair required)

| method | reason to avoid |
|---|---|
| `dlmmPool.initializePositionAndAddLiquidityByStrategy` | requires Keypair for position, user public key, sender, etc. |
| `dlmmPool.addLiquidityByStrategy` | same |
| `dlmmPool.removeLiquidity` | same |
| `dlmmPool.swap` (tx builder) | constructs Transaction |
| `dlmmPool.closePosition` | constructs Transaction |
| `dlmmPool.claimFee` | constructs Transaction |
| `dlmmPool.claimReward` | constructs Transaction |

→ All these methods **import or reference Keypair**, but the read-only path (create → getActiveBin → getFeeInfo → getBinArrayForSwap → swapQuote) does **NOT** invoke them.

## 4. Wallet-related import analysis

| item | present? | where | used by us? |
|---|---|---|---|
| `import { Keypair, ... } from "@solana/web3.js"` | YES | index.mjs line 3 | NO (we never instantiate Keypair) |
| `import { Keypair, ... } from "@solana/web3.js"` (Anchor) | YES | index.mjs line 10250 | NO |
| `import "@solana/wallet-adapter-react"` | **NO** | not in any dist file | n/a |
| `import "@solana/wallet-adapter-wallets"` | **NO** | not in any dist file | n/a |
| `localStorage.setItem(...)` (wallet persist) | NO | n/a | n/a |
| `window.solana` (browser wallet) | NO | n/a | n/a |

**结论**: SDK **不**带 wallet-adapter; Keypair 导入**仅**用于**pos-create** methods; 我们的 read-only smoke 完全不触发 Keypair 路径.

## 5. Required dependencies (transitive)

| package | version | role |
|---|---|---|
| @coral-xyz/anchor | 0.31.0 | program derivation, account fetch, struct layout |
| @coral-xyz/borsh | 0.31.0 | binary serialization |
| @solana/spl-token | ^0.4.6 | mint/ATA helpers |
| @solana/web3.js | ^1.91.6 | Connection, PublicKey, AccountMeta, etc. |
| bn.js | ^5.2.1 | big numbers |
| decimal.js | ^10.4.2 | decimal math |
| express | ^4.19.2 | (optional, not used in read-only path) |
| gaussian | ^1.3.0 | (for distribution strategies) |

→ **不**包含 wallet-adapter; **不**包含 keychain/keystore; **不**包含 secret manager.

## 6. 严格只读边界 (本轮已遵守)

```text
× 未在 repo root 安装任何 npm package
× 未 import @solana/wallet-adapter-*
× 未 instantiate Keypair
× 未调用任何 pos-create / tx-builder method
× 未调用 sendTransaction
× 未 swap / open_lp / close_lp / collect_fee / bridge
× 未启动 live/canary/paper
× 未修改 EVM executor v2
× send hard-disable 仍存在（未解除）
× repo root 的 scripts/ 和 tests/ 不动
× 仅在 /tmp/lpbot_meteora_dlmm_sdk_probe_${RUN_ID}/ 安装
```

## 7. 安全断言

```text
install_in_isolated_tmp_dir    = true
repo_root_touched              = false
repo_node_modules_created      = false
wallet_adapter_imported        = false
keypair_instantiated           = false
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 8. 下一阶段

进入 Stage D — known-pool feed freeze (用 V2 smoke pool + SDK example pool 冻结 1+ 个 known pool).
