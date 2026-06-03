# Meteora Survival EV Inputs — Stage D

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. Model dimensions

| dim | values | count |
|---|---|---|
| notionals_usd | 10, 20, 100, 500, 1000, 2000 | 6 |
| hold_windows | 15m, 30m, 1h, 2h, 6h, 24h, 7d | 7 |
| scenarios | zero_il_lvr, optimistic, realistic, conservative | 4 |
| total cells | 6 × 7 × 4 | **168** |

## 1. Input assets (X/USDC only)

### 1.1 Quote data (V6 reused)

| notional | amount_out_raw | effective_rate (1 X / USDC) | confidence |
|---|---|---|---|
| 10U | 941005 | 0.09410 (1 X ≈ 10.62 USDC) | 0.85 |
| 20U | 1882010 | 0.09410 (1 X ≈ 10.62 USDC) | 0.85 |
| 100U | (extrapolated linear; 9410050 raw X) | 0.09410 | 0.85 (extrapolated) |
| 500U | (extrapolated linear; 47050250 raw X) | 0.09410 | 0.85 (extrapolated) |
| 1000U | (extrapolated linear; 94100500 raw X) | 0.09410 | 0.85 (extrapolated) |
| 2000U | (extrapolated linear; 188201000 raw X) | 0.09410 | 0.85 (extrapolated) |

- price_impact field is empty in V6 quote; mark `missing`.

### 1.2 Pool snapshot (V4 reused)

| field | value |
|---|---|
| pool_address | `9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad` |
| active_bin_id | -236 |
| bin_step | 100 |
| active_price | 0.095533521620978319249 |
| token_x_decimals | 6 |
| token_y_decimals | 6 |
| reserve_x_raw | 101593140348172 |
| reserve_y_raw | 2200122802740 |

### 1.3 Fee snapshot (V4 reused)

| field | value |
|---|---|
| base_fee_bps | 1.5 |
| max_fee_bps | 10 |
| protocol_fee_bps | missing (SDK returned undefined; not in model) |
| confidence | 0.95 |

### 1.4 Bin liquidity (V6 reused)

| metric | value |
|---|---|
| bins_with_liquidity_at_5_arrays | 231 |
| total_bins_at_5_arrays | 280 |
| active_bin_distance | estimated 0-1 bin (active bin -236 has neighboring bins with liquidity per V6 decode) |

## 2. Per-cell input sources

| input | source | notes |
|---|---|---|
| quote_amount_out | raw X amount out (extrapolated from V6 10U/20U points; linear scaling) | per notional |
| quote_price_impact | missing (V6 has no price_impact; mark missing) | — |
| fee_base | 1.5 bps (V4 fee snapshot) | — |
| fee_max | 10 bps (V4 fee snapshot) | — |
| active_bin | -236 (V4 pool snapshot) | — |
| bin_step | 100 (V4 pool snapshot) | — |
| available_liquidity_proxy | 0.0001 * reserve_x_raw (heuristic; 0.01% of pool reserves per hold window) | heuristic |
| round_trip_cost_proxy | 0.001 (0.1% per round trip; heuristic) | heuristic |
| solana_tx_fee_proxy | 5000 lamports = 0.000005 SOL (heuristic; base fee; Solana network default) | heuristic |
| account_rent_cost_proxy | 0.00218928 SOL (heuristic; rent for token account + position account) | heuristic |
| position_setup_cost_proxy | 0 (no signers; this is a model only) | heuristic |
| exit_cost_proxy | 0.0001 (0.01% per exit; heuristic) | heuristic |
| data_confidence | 0.5 (heuristic-based; mark data_confidence=low for scenario-based fee capture) | — |

### 2.1 IL/LVR proxies by scenario

| scenario | proxy |
|---|---|
| zero_il_lvr | 0 (counterfactual; no IL/LVR) |
| optimistic | 0.001 (0.1% IL + 0.0% LVR) |
| realistic | 0.005 (0.5% IL + 0.0% LVR for tight liquidity; +0.0% LVR for active bin) |
| conservative | 0.020 (2.0% IL + 0.0% LVR for wide price swings) |

## 3. Missing data must mark (per spec)

- `actual_on_chain_trading_volume`
- `actual_realized_il_lvr`
- `actual_realized_slippage`
- `actual_solana_priority_fee`
- `actual_rent_amount`
- `real_token_usdc_supply`

These are NOT filled with 0. They are marked `missing` or proxied with explicit `heuristic=true` label.

## 4. This stage does NOT

- fill missing data with zero
- claim EV for SOL/USDC (no_quote_data)
- represent partial as full
- load any keypair / private key
- construct any transaction

## 5. Safety assertions

```text
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
v2_line_count_unchanged          = true (992)
data_confidence                  = 0.5 (heuristic-based; low)
```

## 6. 下一阶段

进入 Stage E — fee capture proxy + Stage F — cost model + Stage G — survival EV preview (all X/USDC only).
