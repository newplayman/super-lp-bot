# Meteora Quote Smoke v3 by Coverage — Stage G

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键结果

```text
quote_attempted         = 12 (3 tiers × 2 pools × 2 notionals)
quote_success           = 6  (50%)
pool_1_sol_usdc         = 0/6 blocked at all tiers
pool_2_x_usdc           = 6/6 STABLE at all tiers
real_quote_data         = 1 X ≈ 10.62 USDC (1/0.0941)
```

## 1. Per-coverage Per-pool Per-notional

| coverage | pool | notional | quote_success | amount_out_raw | blocker |
|---|---|---|---|---|---|
| 5_arrays | pool 1 (SOL/USDC) | 10U | ❌ | null | Insufficient liquidity in binArrays |
| 5_arrays | pool 1 | 20U | ❌ | null | Insufficient liquidity in binArrays |
| 5_arrays | pool 2 (X/USDC) | 10U | ✅ | **941005** | — |
| 5_arrays | pool 2 | 20U | ✅ | **1882010** | — |
| 7_arrays | pool 1 | 10U | ❌ | null | Insufficient liquidity in binArrays |
| 7_arrays | pool 1 | 20U | ❌ | null | Insufficient liquidity in binArrays |
| 7_arrays | pool 2 | 10U | ✅ | **941005** | — |
| 7_arrays | pool 2 | 20U | ✅ | **1882010** | — |
| 9_arrays | pool 1 | 10U | ❌ | null | Insufficient liquidity in binArrays |
| 9_arrays | pool 1 | 20U | ❌ | null | Insufficient liquidity in binArrays |
| 9_arrays | pool 2 | 10U | ✅ | **941005** | — |
| 9_arrays | pool 2 | 20U | ✅ | **1882010** | — |

## 2. 关键 finding: pool 1 quote blocked at ALL coverage tiers

### 2.1 原因分析

- pool 1 (SOL/USDC) bin_step=2: tight spacing; 0.02% per bin
- 9 arrays × 70 bins = 630 bins ≈ 12% price range
- SDK swapQuote requires **consecutive** bin arrays with liquidity in the swap path
- pool 1's liquidity at active_bin_id=-12248: **not in the ±6% range from active bin**
- Need >9 arrays OR paid RPC GPA to find liquidity

### 2.2 V5 → V6 实际 progress

| metric | V5 (3 arrays) | V6 (9 arrays) | delta |
|---|---|---|---|
| pool 1 quote | 0/2 | 0/6 | unchanged (blocked; just more attempts) |
| pool 2 quote | 2/2 | 6/6 | 3x (stable) |
| Total quote success | 2/4 | 6/12 | 3x (pool 2 only) |

## 3. 真实链上 quote data (pool 2)

- 10U USDC → 941,005 raw X (Y to X swap)
- 20U USDC → 1,882,010 raw X (linear 2x)
- **1 X ≈ 10.62 USDC** (1/0.0941) for pool 2 at 2026-06-03 14:44 UTC

## 4. 严格只读边界

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

## 5. 安全断言

```text
quote_via_sdk_swapQuote        = true (returns quote object; no tx)
no_swap_tx_builder_called     = true
no_keypair_instantiated        = true
no_wallet_adapter_imported     = true
no_transaction_sent            = true
solana_wallet_or_keypair_touched = false
can_run_probe_now              = false
v2_line_count_unchanged        = true (992)
```

## 6. 下一阶段

进入 Stage H — quote readiness update: 6 表状态判定 + can_enter_survival_ev_preview yes/no.
