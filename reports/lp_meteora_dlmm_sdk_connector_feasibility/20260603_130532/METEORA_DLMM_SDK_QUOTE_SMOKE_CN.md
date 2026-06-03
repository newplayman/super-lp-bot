# Meteora DLMM SDK Quote Smoke (Read-Only) — Stage F

- stage: `LP_METEORA_DLMM_SDK_API_CONNECTOR_FEASIBILITY_FIX_REPEAT_V1`
- run_id: `20260603_130532`

## 0. 关键结果

```text
quote_attempted                = 4 (2 pools × 2 notionals: 10U, 20U USDC)
quote_success_count            = 0
quote_blocker                  = public RPC returns 403 Forbidden on getBinArrayForSwap
quote_blocker_summary          = bin arrays NOT fetchable on public RPC; needed by swapQuote
swapQuote_sdk_call_ready       = true (verified by import; we did NOT call it without bin arrays)
```

## 1. 真实 attempted results (4/4 阻断)

| pool | notional | quote_success | error_stage | error_short | latency_ms |
|---|---|---|---|---|---|
| `5BKxfWMb...` | 10 USDC | ❌ | getBinArrayForSwap | 403 Forbidden | 7959 |
| `5BKxfWMb...` | 20 USDC | ❌ | getBinArrayForSwap | 403 Forbidden | 6814 |
| `9DiruRpj...` | 10 USDC | ❌ | getBinArrayForSwap | 403 Forbidden | 6560 |
| `9DiruRpj...` | 20 USDC | ❌ | getBinArrayForSwap | 403 Forbidden | 6750 |

## 2. 根因分析 (per spec "如果 SDK 调用失败，必须给 root cause")

### 2.1 错误链

`dlmmPool.swapQuote(inAmount, swapYtoX, slippage, binArrays, isPartialFill, maxExtraBinArrays)` requires `binArrays: BinArrayAccount[]` as a 4th arg. These are the bin array accounts covering the swap path (near active bin + bins to be crossed).

`dlmmPool.getBinArrayForSwap(swapYtoX, count)` is the SDK helper that derives the bin array PDAs from active bin and fetches them. This is the ONLY built-in way to get bin arrays via the SDK without computing PDAs manually.

### 2.2 `getBinArrayForSwap` 内部实现 (从 SDK 源码)

```ts
// @meteora-ag/dlmm/src/dlmm/index.ts (or dist/index.js:13671)
getBinArrayForSwap(swapForY: boolean, count?: number): Promise<BinArrayAccount[]>
```

Under the hood:
1. Calls `getActiveBin()` (which does `program.account.lbPair.fetch(this.pubkey)` + `getBins(this.pubkey, activeId, activeId, ...)`)
2. Reads the `binArrayBitmap` from `lbPair` to find next bin array with liquidity
3. Calls `chunkedGetMultipleAccountInfos(connection, binArrayPubkeys)` — **THIS is where public RPC returns 403**

`chunkedGetMultipleAccountInfos` is a chunked variant of `connection.getMultipleAccountsInfo` that asks the RPC for many accounts in one request. **Public RPCs restrict this**: publicnode returned `403 Forbidden: "blocked parameter: params.0.#"`, mainnet-beta returned `410 Gone: "The RPC call or parameters have been disabled"`.

### 2.3 推断 root cause

- **Public RPCs cap or block `getMultipleAccounts` for many accounts at once**
- Meteora DLMM requires fetching several bin array accounts (each is a 904-byte account)
- The SDK's chunked helper hits the cap
- **NOT a SDK bug**; **NOT an account missing**; **public RPC restriction**

### 2.4 候选解 (operator input required)

| 解 | 描述 | 状态 |
|---|---|---|
| paid RPC (Helius / Triton / QuickNode) | has higher caps; same `getMultipleAccounts` call works | 需 operator 提供 key |
| known bin array index | pass a pre-computed BinArrayAccount[] directly to swapQuote, bypassing getBinArrayForSwap | 需 operator 提供 bin array 数据 (cache / indexer) |
| Solana getProgramAccounts with paid RPC | back to GPA path | needs paid RPC |
| smaller swap (single bin) | swap within active bin; doesn't need bin arrays | theoretical; SDK API may not support directly |

## 3. SDK 路径 ready-ness (honest)

| SDK method | ready? | 备注 |
|---|---|---|
| `dlmmPool.swapQuote(...)` | **ready** (imports + type-defs confirmed) | 需要外部 bin arrays |
| `getBinArrayForSwap` | blocked on public RPC | 需 paid RPC |
| Direct `swapExactInQuoteAtBin` (helper) | **ready** (exported) | 需手算 bin ID + bin array content |
| `binIdToBinArrayIndex` | **ready** | helper; no RPC |

→ SDK code path **is** ready; the **blocker** is **public RPC method restriction**, identical to V1's GPA blocker.

## 4. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不调用 sendTransaction
- ❌ 不调用 swap (tx builder) — we only call read-only `swapQuote`
- ❌ 不 open LP / close LP / collect fee / bridge
- ❌ 不调用 wallet adapter
- ❌ 不 paid RPC call (无 key)
- ❌ 不 webfetch / web search

## 5. 安全断言

```text
smoke_read_only        = true
no_keypair_used        = true
no_signer_used         = true
no_wallet_adapter      = true
no_transaction_built   = true
no_sendTransaction     = true
solana_wallet_or_keypair_touched = false
transaction_sent       = false
can_run_probe_now      = false
v2_line_count_unchanged = true (992)
```

## 6. 下一阶段

进入 Stage G — known-pool connector schema v1 (6 张 research-only 表). 既然 quote 在 public RPC 上**不可行**, connector schema 必须明确 quote 字段为 `quote_blocked_by_bin_arrays`; connector 实现阶段**可以**用 paid RPC 解决.
