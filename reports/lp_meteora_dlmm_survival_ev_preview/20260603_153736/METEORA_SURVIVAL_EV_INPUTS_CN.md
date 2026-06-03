# Meteora Survival EV Inputs — Stage D

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- scope: **partial_pool2_only (X/USDC)**

## 0. 关键输入

```text
rows_expected = 168 (6 notionals × 7 hold_windows × 4 scenarios)
quote source  = V6 (meteora_quote_smoke_v2.json)
pool source   = V4 (meteora_pool_snapshot.json)
fee source    = V4 (meteora_fee_snapshot.json)
bin liq proxy = V6 (231 bins with liquidity at 5_arrays)
all heuristic_marked = true (no real volume / no realized IL data)
```

## 1. Input Assets (from V6+V4 evidence)

| asset | value | source |
|---|---|---|
| x_usdc_quote 10U | out=941005 raw X (6-dec); rate=0.09410 X/USDC | V6 |
| x_usdc_quote 20U | out=1882010 raw X; rate=0.09410 (linear) | V6 |
| x_usdc active_bin_id | -236 | V4 |
| x_usdc bin_step | 100 | V4 |
| x_usdc active_price | 0.095533521620978319249 | V4 |
| x_usdc reserve_x_raw | 101593140348172 | V4 |
| x_usdc reserve_y_raw | 2200122802740 | V4 |
| x_usdc base_fee_bps | 1.5 | V4 |
| x_usdc max_fee_bps | 10 | V4 |
| x_usdc protocol_fee_bps | **missing** (SDK undefined; we have no fallback) | V4 |
| x_usdc bins_with_liquidity | 231/280 (5_arrays) | V6 |
| x_usdc price_impact | **missing** (V6 has no field) | V6 |
| x_usdc actual_volume | **missing** (not measured; use scenario-based proxy) | — |
| x_usdc actual_il_lvr | **missing** (not measured; use scenario-based proxy) | — |

## 2. Model Dimensions

| dimension | values | count |
|---|---|---|
| notionals_usd | [10, 20, 100, 500, 1000, 2000] | 6 |
| hold_windows | [15m, 30m, 1h, 2h, 6h, 24h, 7d] | 7 |
| scenarios | [zero_il_lvr, optimistic, realistic, conservative] | 4 |
| **total cells** | | **168** |

## 3. Per-Cell Inputs

| field | source/value | data_confidence |
|---|---|---|
| quote_amount_out | extrapolated from V6 10U/20U points; linear scaling for other notionals | 0.85 |
| quote_price_impact | **missing** (V6 has no field) | 0.0 |
| fee_base | 1.5 bps (V4) | 0.95 |
| fee_max | 10 bps (V4) | 0.95 |
| active_bin | -236 (V4) | 1.0 |
| bin_step | 100 (V4) | 1.0 |
| available_liquidity_proxy | 0.0001 × reserve_x_raw (heuristic; 0.01% of pool reserves) | 0.3 (heuristic) |
| round_trip_cost_proxy | 0.001 (0.1% per round trip; heuristic) | 0.3 (heuristic) |
| solana_tx_fee_proxy | 5000 lamports = 0.000005 SOL (heuristic; base fee) | 0.5 (heuristic) |
| account_rent_cost_proxy | 0.00089 SOL (heuristic; rent for account creation) | 0.5 (heuristic) |
| position_setup_cost_proxy | 0 (no signers; model only) | 0.9 (no cost) |
| exit_cost_proxy | 0.0001 (0.01% per exit; heuristic) | 0.3 (heuristic) |
| il_lvr_proxy (zero_il_lvr) | 0 | 0.5 (counterfactual) |
| il_lvr_proxy (optimistic) | 0.001 (0.1%) | 0.3 (heuristic) |
| il_lvr_proxy (realistic) | 0.005 (0.5%) | 0.3 (heuristic) |
| il_lvr_proxy (conservative) | 0.020 (2.0%) | 0.3 (heuristic) |

## 4. Missing Fields (per spec: must mark "missing", not 0)

- actual_on_chain_trading_volume
- actual_realized_il_lvr
- actual_realized_slippage
- actual_solana_priority_fee
- actual_rent_amount
- real_token_usdc_supply

## 5. Notional scaling rule

V6 has 10U and 20U quotes. For other notionals (100, 500, 1000, 2000), we use:
- linear scaling: `quote_amount_out = raw_X_out_at_10U × (notional / 10)`
- This is an approximation; **not** real on-chain quote (we don't have a paid RPC to do 100U+ on-chain)
- **Mark data_confidence=0.4 for notionals > 20U** (extrapolated, not measured)

## 6. 不在本阶段做

- ❌ 不把 missing 字段填 0
- ❌ 不 fake data
- ❌ 不 compute EV for SOL/USDC (no_quote_data)
- ❌ 不 represent partial as full
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不修改 EVM executor v2

## 7. 安全断言

```text
this_stage_only_input_build = true
heuristic_marked = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 8. 下一阶段

进入 Stage E — fee capture proxy (scenario-based; heuristic marked) + Stage F — cost model + Stage G — survival EV preview (168 cells computed).
