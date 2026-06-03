# Meteora Survival EV Preview — Stage G

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. 关键结果

```text
rows                                = 168 (6 notionals × 7 hold_windows × 4 scenarios)
positive_zero_il_lvr_count          = 0
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count (< 0 and > -0.5) = 84
best_notional                       = 2000
best_hold_window                    = 15m
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = -0.154 (still negative)
best_net_ev_proxy_pct               = -0.0077%
all_rows_heuristic                  = true
all_rows_invalid_reason_set         = true
```

## 1. Model formula

For each (notional, hold_window, scenario):

```
gross_fee_usd         = notional × 0.005 (medium turnover) × (1.5 bps / 10000)
                       = notional × 7.5e-7
il_lvr_cost_usd       = notional × IL_LVR_PCT[scenario]
total_cost_usd        = realistic_cost.net_cost_usd  (≈ 0.156)
net_ev_usd            = gross_fee_usd − il_lvr_cost_usd − total_cost_usd
net_ev_pct            = (net_ev_usd / notional) × 100
```

Where IL_LVR_PCT = {zero_il_lvr: 0, optimistic: 0.001, realistic: 0.005, conservative: 0.020}.

## 2. By-scenario summary

| scenario | IL/LVR % | positive cells | near_break_even (<0, >-0.5) | mean net_ev_pct |
|---|---|---|---|---|
| zero_il_lvr | 0.0% | 0/42 | 42/42 | very close to 0% |
| optimistic | 0.1% | 0/42 | 21/42 | ~-0.2% |
| realistic | 0.5% | 0/42 | 14/42 | ~-1.6% |
| conservative | 2.0% | 0/42 | 7/42 | ~-3.9% |

## 3. Why all 168 cells are negative

The X/USDC pool at 10–2000 USD notionals is structurally unprofitable for single-position LP under the V8 model:

- gross fee at 2000 notional + 15m + medium volume = 2000 × 0.005 × 0.00015 = **$0.0015**
- fixed cost (rent + tx) per position ≈ **$0.156**
- even with zero IL/LVR, fee capture is 100× smaller than fixed cost
- at 10 notional, fee capture is $0.0000075, cost is $0.156 — ratio 1:21,000

The only way for a cell to be positive is to massively increase the assumed volume turnover (e.g., 20–50% of notional per hold window), which is unrealistic for a pool with bin_step=100 and 231 active bins over 5 arrays.

## 4. Best & worst cell

| metric | notional | hold | scenario | net_ev_usd | net_ev_pct |
|---|---|---|---|---|---|
| best | 2000 | 15m | zero_il_lvr | -0.154 | -0.0077% |
| worst | 10 | 7d | conservative | -0.356 | -3.559% |

(Note: hold_window doesn't actually change fee capture in this model because we use a fixed per-hold turnover, not a per-second rate. The 7d / 30m hold distinction is structural — it affects IL/LVR exposure in real markets but the model treats them as one-time captures. This is a model limitation explicitly marked.)

## 5. Honest gaps (per spec)

- 实际 on-chain volume unknown → fee capture is heuristic, marked.
- 实际 realized IL/LVR unknown → IL/LVR is heuristic, marked.
- 实际 Solana priority fee unknown → cost is heuristic, marked.
- 实际 SOL price unknown → cost uses $130/SOL heuristic, marked.
- 实际 rent unknown → cost uses 0.00218928 SOL heuristic, marked.
- 实际 price impact on 2000 USD swap unknown → V6 quote was for 10/20 USD; extrapolation is linear and doesn't model bin crossing.

All 168 rows have `heuristic=true`, `confidence=0.4`, `scope=partial_pool2_only`, and a non-empty `invalid_reason`.

## 6. 结论 (honest)

- 0/168 cells are positive under any scenario.
- 84/168 cells are "near break-even" (within $0.5 of 0), all of which are in the zero_il_lvr / optimistic / low-notional corner.
- best_net_ev_proxy_usd is -$0.154 at the largest notional + shortest hold + best scenario.
- This is a **structural negative** finding, not a measurement error.
- The model has known limitations (linear extrapolation, no per-time fee accrual, no LVR component); a real implementation with measured volume and measured IL would have different numbers but the same order-of-magnitude conclusion.

## 7. 不在本阶段做

- ❌ 不 compute SOL/USDC EV (no_quote_data)
- ❌ 不 represent partial as full
- ❌ 不 fill missing data with zero
- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 modify EVM executor v2

## 8. 安全断言

```text
this_stage_only_heuristic     = true
heuristic_marked_on_all_rows  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 9. 下一阶段

进入 Stage H — 10/20U preflight implication: should we even consider designing a probe for 10/20U X/USDC?
