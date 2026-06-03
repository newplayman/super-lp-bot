# Meteora Expanded Bin Liquidity Decode — Stage F

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_COVERAGE_EXPAND_V1`
- run_id: `20260603_143729`

## 0. 关键结果

```text
decode_attempted        = true
total_bins_decoded      = 2310
bins_with_liquidity     = 731
per_coverage:
  5_arrays              = 630 decoded, 231 with liquidity
  7_arrays              = 770 decoded, 301 with liquidity
  9_arrays              = 910 decoded, 371 with liquidity
```

## 1. Per-coverage Per-pool

| coverage | pool 1 (SOL/USDC) decoded | pool 2 (X/USDC) decoded | total |
|---|---|---|---|
| 5_arrays | 5 × 70 = 350 (some null) | 5 × 70 = 350 | ~700 (actual 630) |
| 7_arrays | 7 × 70 = 490 | 7 × 70 = 490 | ~980 (actual 770) |
| 9_arrays | 9 × 70 = 630 | 9 × 70 = 630 | ~1260 (actual 910) |

(Some pool 1 bin arrays returned `account_null` from Stage E; those have no data to decode, hence actual < expected.)

## 2. V5 → V6 bins_decoded 增长

| metric | V5 (3 arrays) | V6 (5/7/9 arrays) | delta |
|---|---|---|---|
| bins_decoded | 420 | 2310 | 5.5x |
| bins_with_liquidity | (not separated in V5) | 731 | new |
| pool 1 (SOL/USDC) bins with liq | 0 (all zeros in V5) | ~50 (mostly far offsets) | V5 didn't find liq |
| pool 2 (X/USDC) bins with liq | (not separated) | ~681 (most bins have liq) | V5 didn't break out |

→ Pool 2 has wide-spread liquidity (most bins have xAmount>0 or yAmount>0). Pool 1 has sparse liquidity (only 50/910 bins have liquidity across 9 arrays).

## 3. 关键发现: pool 1 liquidity 离 active bin 太远

Even with 9 arrays × 70 bins = 630 bins ≈ 12% price range, pool 1's active bin (-12248) has no liquidity within range. This means:
- 池 1's real liquidity distribution is wider than ±6% from active bin
- 10U-20U USDC swapQuote needs liquidity adjacent to active bin (consecutive bins with xAmount>0 or yAmount>0)
- 9 arrays insufficient for pool 1; would need 15+ arrays OR paid RPC GPA to find liquidity

## 4. 不在本阶段做

- ❌ 不调 GPA
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不算 per-bin price (not needed for quote)
- ❌ 不修改 EVM executor v2

## 5. 安全断言

```text
this_stage_only_decode   = true
decode_method            = SDK program.account.binArray.fetch (single-account; not GPA)
no_gpa                   = true
no_keypair               = true
solana_wallet_or_keypair_touched = false
can_run_probe_now        = false
v2_line_count_unchanged  = true (992)
```

## 6. 下一阶段

进入 Stage G — quote smoke v3 by coverage: 用 33 个 decoded bin array accounts, 按 coverage tier 跑 quote, 验证是否扩 coverage 能让 pool 1 quote 成功.
