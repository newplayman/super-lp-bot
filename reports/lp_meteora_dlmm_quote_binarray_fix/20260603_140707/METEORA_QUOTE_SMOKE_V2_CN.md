# Meteora Quote Smoke v2 — Stage H

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 关键结果

```text
quote_attempted         = true
quote_results           = 4 (2 pools × 2 notionals: 10U, 20U USDC)
quote_success           = 2 (50%)
quote_blocked           = 2 (50%)
rpc_method_used         = SDK dlmmPool.swapQuote with multi-bin-array (single-account decoded)
```

→ V5 **首次** 成功 quote (V1-V4 全部 0%). 2/4 success in single pool.

## 1. Per-attempt 结果

| pool | notional | token_in | token_out | quote_success | amount_out_raw | fee | bins_crossed | reason |
|---|---|---|---|---|---|---|---|---|
| pool 1 (SOL/USDC) | 10U | Y (USDC) | X (SOL) | ❌ | null | null | 0 | "Insufficient liquidity in binArrays" (active_bin too far from liquidity) |
| pool 1 | 20U | Y (USDC) | X (SOL) | ❌ | null | null | 0 | same |
| pool 2 (X/USDC) | 10U | Y (USDC) | X | ✅ | **941005** | null | 0 | real quote |
| pool 2 | 20U | Y (USDC) | X | ✅ | **1882010** | null | 0 | real quote (linear: 20U = 2×10U out) |

## 2. 关键发现

### 2.1 Single-account path 完全 work

- **6/6** bin array PDAs derived (no RPC)
- **6/6** single-account `getAccountInfo` success on public RPC (V4's blocker **bypassed**)
- **420 bins** decoded via SDK `program.account.binArray.fetch`
- **2/4** quote success via `dlmmPool.swapQuote` with 3 decoded bin arrays

### 2.2 Pool 1 vs Pool 2 差异

| pool | bin_step | active_bin | result | 解释 |
|---|---|---|---|---|
| pool 1 (SOL/USDC) | 2 | -12248 | ❌ | bin_step=2 是 tight spacing; 3 bin arrays × 70 bins = 210 bins = 0.42% price range; 10U USDC swap 可能需要更大范围 |
| pool 2 (X/USDC) | 100 | -236 | ✅ | bin_step=100 是 wide spacing; 210 bins ≈ 21000% range; 完全覆盖 swap path |

→ **bin_step 决定 quote 是否能 fit in 3 bin arrays**.

### 2.3 V4 → V5 关键解锁

- V4 (multi-account via `getBinArrayForSwap`): 0/4 quote (403 RPC blocker)
- V5 (single-account via `connection.getAccountInfo`): 2/4 quote

→ Single-account path **unlocks 50% of quotes without paid RPC**.

## 3. Root cause: "Insufficient liquidity in binArrays" (pool 1)

- pool 1 (SOL/USDC) bin_step=2 means each bin = ~0.02% price change
- 3 bin arrays × 70 bins = 210 bins = ~4.2% price range
- 10U USDC swap may need more bins depending on liquidity distribution
- Fix: extend coverage to **more bin arrays** (e.g. 5-7 arrays, or active ± 100 bins via deriveBinArray active_index ± 100/64)

→ **Not a paid RPC requirement**, just need more bin arrays.

## 4. Real on-chain quote data (pool 2)

| notional | amount_in | amount_out | effective_rate |
|---|---|---|---|
| 10U USDC | 10_000_000 (6-dec USDC) | 941,005 (6-dec X) | 0.0941 X/USDC |
| 20U USDC | 20_000_000 | 1,882,010 | 0.0941 X/USDC (linear) |

→ **1 X ≈ 10.62 USDC** (1/0.0941) for this pool at 2026-06-03 14:17 UTC.

## 5. 严格只读边界

```text
× 未 instantiate Keypair
× 未构造 transaction
× 未调用 sendTransaction
× 未调用 swap tx builder
× 未调 open_lp / close_lp / collect_fee
× 未 paid RPC
× 未 import @solana/wallet-adapter-*
× 未桥接
× 未启动 live/canary/paper
× 未修改 EVM executor v2
```

## 6. 安全断言

```text
quote_via_sdk_swapQuote       = true (returns quote object; no tx)
no_swap_tx_builder_called     = true
no_keypair_instantiated        = true
no_wallet_adapter_imported     = true
no_transaction_sent            = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 7. 下一阶段

进入 Stage I — paid RPC requirement decision. 关键判定:
- 2/4 quote success: **partial** (not 100% but proves single-account path works for some pools)
- paid_rpc_required: **partial** (only needed for pools with tight bin_step OR if we want full bin liquidity across larger range)
- 替代 fix: 扩展 bin array 覆盖范围 (active_index ± 100) 而**不**用 paid RPC
