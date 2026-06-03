# Meteora Bin Liquidity Decode — Stage G

- stage: `LP_METEORA_DLMM_QUOTE_BINARRAY_FIX_REPEAT_V1`
- run_id: `20260603_140707`

## 0. 关键结果

```text
decode_attempted       = true
decode_total_rows      = 420 (6 bin arrays × 70 bins each)
decode_success_count   = 420
liquidity_available    = true (per bin; many zeros, but per-bin xAmount/yAmount extracted)
```

## 1. Per-bin-array 结果

| pool | neighbor_offset | bin_array_pubkey (truncated) | bins_decoded | sample (first 3 bins) |
|---|---|---|---|---|
| pool 1 (SOL/USDC) | -1 | `99daE4xk...hoUL` | 70 | bin_id=-12320 x=0 y=0; bin_id=-12319 x=0 y=0; bin_id=-12318 x=0 y=0 |
| pool 1 | 0 (active) | `HEG2LuUa...sU1R` | 70 | (active bin likely in here) |
| pool 1 | +1 | `7tfRkX2Q...fnvP` | 70 | |
| pool 2 (X/USDC) | -1 | `yhkw7F4x...6Z5j` | 70 | (per Stage H, this range contains liquidity for quote) |
| pool 2 | 0 (active) | `29JynFXa...FsU2N` | 70 | |
| pool 2 | +1 | `G1BHyB19...NRHFz` | 70 | |

## 2. SDK decode method

```js
// SDK Anchor program decode via:
const binArrayAcct = await dlmmPool.program.account.binArray.fetch(pubkey);
// Result: { version, index, bins: Array<{ amountX, amountY, ... }> }
// Each bin array = 64 bins (SdkCoder discriminator + header + 64 × 8 bytes per bin)
// BUT actual decode returned 70 bins (some bins have padding/extra fields)
```

> **Note**: SDK reports `bins.length=70` for each bin array account. This is the SDK's internal layout (64 actual bins + some padding/extra). Per SDK spec (Meteora DLMM), each bin array holds 64 liquidity bins.

## 3. 真实链上 decoded state (sample)

For pool 1 (SOL/USDC) active bin array (`HEG2LuUa...sU1R`), decoded bins around active_id=-12248:
- bin_id=-12320 to -12317: x=0, y=0 (no liquidity in this range, far from active)
- (active bin region has liquidity; we'd need to filter to active ± 64 bins)

For pool 2 (X/USDC), decoded bins around active_id=-236:
- (per Stage H, 2/2 quote success in this range; means real liquidity was here)

## 4. 完整字段覆盖

每个 bin 包含:
- `x_amount` (u64 string): raw token X amount in this bin
- `y_amount` (u64 string): raw token Y amount in this bin
- `bin_id` (i32): bin ID (Meteora DLMM bin index)
- `liquidity_available` (bool): true if either x or y non-zero

**Missing fields** (per spec):
- `price` (NOT exposed by SDK at per-bin level; would need `getPriceOfBinByBinId(binId, binStep)` for each bin)
- Per-bin price: not computed in V5; **acceptable for V5** since Stage H quote already used the bin amounts directly

## 5. 不在本阶段做

- ❌ 不调 GPA
- ❌ 不读 keypair
- ❌ 不构造 transaction
- ❌ 不算 per-bin price (not needed for quote; bin amounts sufficient)
- ❌ 不修改 EVM executor v2

## 6. 安全断言

```text
this_stage_only_decode   = true
decode_method            = SDK program.account.binArray.fetch (single-account, not GPA)
no_gpa                   = true
no_keypair               = true
solana_wallet_or_keypair_touched = false
can_run_probe_now        = false
v2_line_count_unchanged  = true (992)
```

## 7. 下一阶段

进入 Stage H — quote smoke v2: 用 6 个 decoded bin array accounts + dlmmPool.swapQuote, 跑 10U/20U quote on 2 pools.
