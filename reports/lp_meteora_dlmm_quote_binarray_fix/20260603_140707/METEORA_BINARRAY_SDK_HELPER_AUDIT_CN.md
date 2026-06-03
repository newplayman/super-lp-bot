# Meteora Bin Array SDK Helper Audit — Stage C

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 关键发现

```text
helpers_audited          = 12
helpers_no_rpc_required  = 7 (binIdToBinArrayIndex, deriveBinArray, deriveBinArrayBitmapExtension, getBinArrayKeysCoverage, getBinArrayLowerUpperBinId, getBinArrayIndexesCoverage, getBinArrayInfoForNonContiguousBinIds, swapQuote)
helpers_multi_account_blocked = 4 (getBinArrayForSwap, getBinArrays, getBinsAroundActiveBin, getBinsBetweenMinAndMaxPrice)
single_account_path_feasible = yes (use binIdToBinArrayIndex + deriveBinArray + connection.getAccountInfo(pubkey))
small_batch_path_feasible    = yes (use connection.getMultipleAccountsInfo([1 pubkey]))
v5_action                    = implement single-account path; if fails, document paid_rpc_required
```

## 1. 关键 SDK helper 详解

### 1.1 纯计算 (no RPC, no wallet, no tx) — 可用

| helper | signature | 用途 |
|---|---|---|
| `binIdToBinArrayIndex` | `(binId: BN) => BN` | given activeBinId, compute binArrayIndex (pure math) |
| `deriveBinArray` | `(lbPair, index, programId) => [PublicKey, bump]` | PDA derivation; deterministic; no RPC |
| `deriveBinArrayBitmapExtension` | `(lbPair, programId) => [PublicKey, bump]` | bitmap extension PDA; not needed for bin array read |
| `getBinArrayKeysCoverage` | `(programId) => PublicKey[]` | returns array of derived pubkeys (no RPC) |
| `getBinArrayLowerUpperBinId` | `(binArrayIndex: BN) => BN[]` | returns [lowerBinId, upperBinId] for a bin array |
| `getBinArrayIndexesCoverage` | `(lowerBinId, upperBinId) => BN[]` | returns array of bin array indices covering range |
| `getBinArrayInfoForNonContiguousBinIds` | `(binIds, programId, lbPair) => { pubkeys, indices }` | derived pubkeys + index info; no RPC |
| `swapQuote` | `(inAmount, swapYtoX, slippage, binArrays, ...) => SwapQuote` | local compute; needs pre-fetched binArrays |

### 1.2 多账户 RPC (V4 blocker, 403 on public RPC) — 不可直接用

| helper | 实现 | blocker |
|---|---|---|
| `getBinArrayForSwap(swapForY, count)` | `chunkedGetMultipleAccountInfos` | 403 on publicnode / 410 on mainnet-beta |
| `getBinArrays()` | `program.account.binArray.all([binArrayLbPairFilter])` = GPA | GPA also blocked |
| `getBinsAroundActiveBin(left, right)` | private `getBins` → `program.account.binArray.fetchMultiple` | multi-account 403 |
| `getBinsBetweenMinAndMaxPrice(min, max)` | same | multi-account 403 |

## 2. single-account path 详细设计

### 2.1 步骤

1. `binIdToBinArrayIndex(activeId)` → `binArrayIndex` (BN)
2. `deriveBinArray(lbPair, binArrayIndex, programId)` → `[binArrayPubkey, bump]`
3. `connection.getAccountInfo(binArrayPubkey)` → single account; should NOT hit 403 (different from getMultipleAccounts)
4. If data returned: decode via SDK (use `program.account.binArray.fetch(pubkey)` or manual layout decode)
5. Pass decoded `BinArrayAccount` to `swapQuote(...)`

### 2.2 邻居 bin arrays

`getBinsAroundActiveBin(64, 64)` would need 3 bin arrays (each holds 64 bins, so +/- 64 bins = 1 active + 0 neighbors). For V5 single-account path, we test:
- Active bin array only (1 account)
- Then 3-account batch (neighbor -1, active, neighbor +1) via getMultipleAccountsInfo
- If both blocked, only paid RPC helps

### 2.3 候选 fallback

| path | 阻断风险 | 期望概率 |
|---|---|---|
| single-account `getAccountInfo` | low | high (80%+) |
| 3-account `getMultipleAccountsInfo` | medium | medium (50%+) |
| GPA on public RPC | high | very low (per V1 0/4 evidence) |

## 3. 已知 dlmm SDK 中"可借鉴"模式

SDK 内部 `binArraysToBeCreate` 方法 (line 22558) 实际**正是**用 `this.program.provider.connection.getMultipleAccountsInfo(binArrays)` 直接调 (3-9 bin arrays 一次性). 这是 SDK 自己**推荐**的 "直接 RPC" 路径, **不**经过 GPA.

V5 可借鉴这个模式: 不调 SDK 的 `getBinArrayForSwap` helper, 直接调 `connection.getMultipleAccountsInfo` with 1-3 个 derived pubkey.

## 4. 不在本阶段做

- ❌ 不安装任何新 package (reuse V3 SDK install in /tmp)
- ❌ 不调任何 RPC (本阶段只 inspect SDK source; Stage D 才 derive PDA)
- ❌ 不构造 transaction
- ❌ 不读 keypair
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
this_stage_only_helper_audit     = true
this_stage_did_not_call_rpc      = true
this_stage_did_not_install_anything = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
v2_line_count_unchanged          = true (992)
```

## 6. 下一阶段

进入 Stage D — active-bin bin array PDA derivation: 写 `scripts/lp_meteora_dlmm_binarray_single_account_probe_v1_readonly.js`, 对 2 known pools 用 binIdToBinArrayIndex + deriveBinArray 推导 active + neighbor -1/+1 bin array pubkey, 输出 CSV/JSON.
