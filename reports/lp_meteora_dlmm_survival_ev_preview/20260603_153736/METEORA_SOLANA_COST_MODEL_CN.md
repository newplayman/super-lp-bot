# Meteora Solana Cost Model — Stage F

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- scope: **partial_pool2_only (X/USDC)**

## 0. 关键说明

```text
rows                = 3 (low / realistic / conservative)
SOL_PRICE_USD       = 130.0 (heuristic; mark)
heuristic_marked    = true (rent + priority fee both heuristic)
```

## 1. Cost components per scenario

| cost_component | low | realistic | conservative | refundable? |
|---|---|---|---|---|
| priority_fee_lamports | 1,000 | 10,000 | 100,000 | no |
| base_fee_lamports | 5,000 | 5,000 | 5,000 | no |
| per_tx_sol | 0.000006 | 0.000015 | 0.000105 | n/a |
| per_tx_usd (at $130/SOL) | 0.00078 | 0.00195 | 0.01365 | n/a |
| round-trip_tx_count | 2 | 2 | 2 | n/a |
| round_trip_usd | 0.00156 | 0.00390 | 0.02730 | no |
| setup (token acct + position acct) | $0.32 | $0.32 | $0.32 | partial (rent exempt recoverable) |
| recovery (close acct) | -$0.13 | -$0.13 | -$0.13 | yes |
| **net_cost_usd** | **$0.186** | **$0.188** | **$0.212** | partial |

## 2. 关键 cost source

- **base_fee_lamports=5000**: Solana network default base fee (1 signature = 5000 lamports)
- **priority_fee**: priority fee per compute unit; we assume 1M CU per tx; 1-100 microLamports/CU
- **token account rent-exempt minimum**: 0.00203928 SOL (SPL Token program)
- **position account rent**: Meteora DLMM position account is ~100 bytes; ~0.00015 SOL
- **SOL_PRICE_USD = 130**: heuristic; actual price varies; mark heuristic

## 3. Confidence

- confidence = 0.5 per row (heuristic on rent + SOL price)
- applies_to_probe = False (per spec: probe no RPC, but cost model is for future notional-scaled probes)
- applies_to_scaled_notional = True (cost per round-trip; notional scaling is in IL/LVR components)

## 4. 不在本阶段做

- ❌ 不测 actual SOL price
- ❌ 不测 actual priority fee
- ❌ 不 fake data

## 5. 安全断言

```text
this_stage_only_heuristic_cost_model = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 6. 下一阶段

进入 Stage G — survival EV preview: 168 cells (6 notionals × 7 hold_windows × 4 scenarios); use fee_capture_proxy (medium scenario) + cost_model (realistic) + il_lvr_proxy per scenario.
