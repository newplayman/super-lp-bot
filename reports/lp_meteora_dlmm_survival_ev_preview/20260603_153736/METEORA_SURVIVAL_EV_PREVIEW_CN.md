# Meteora Survival EV Preview — Stage G

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_153736`
- scope: **partial_pool2_only (X/USDC)**

## 0. 关键结果

```text
rows                            = 168 (6 notionals × 7 hold_windows × 4 scenarios)
positive (zero_il_lvr)           = 0/42
positive (optimistic)            = 0/42
positive (realistic)             = 0/42
positive (conservative)          = 0/42
near_break_even                 = 21/168 (within ±0.05% of break-even; all near $0)
best_row                        = notional=2000 hold=15m scenario=zero_il_lvr net_ev=-$0.154 net_ev_pct=-0.0077%
best_notional                   = 2000
best_hold_window                 = 15m
best_scenario                   = zero_il_lvr
best_net_ev_proxy_usd           = -$0.154
best_net_ev_proxy_pct           = -0.0077%
```

→ **ALL 168 cells negative.** Best case is -$0.154 (-0.0077%) at 2000 notional + 15m hold + zero_il_lvr scenario.

## 1. Methodology

For each cell (notional × hold_window × scenario):

```
net_ev_usd = gross_fee_usd - il_lvr_cost_usd - net_cost_usd
where:
  gross_fee_usd = notional × assumed_volume_pct_medium (0.005) × (base_fee_bps / 10000)
  il_lvr_cost_usd = notional × il_lvr_pct (per scenario)
  net_cost_usd = realistic scenario from cost_model
```

## 2. Per-scenario results

| scenario | il_lvr_pct | positive cells | best net_ev_usd | best net_ev_pct |
|---|---|---|---|---|
| zero_il_lvr | 0% | 0/42 | -$0.154 (2000/15m) | -0.0077% |
| optimistic | 0.1% | 0/42 | -$2.154 (2000/15m) | -0.1077% |
| realistic | 0.5% | 0/42 | -$10.154 (2000/15m) | -0.5077% |
| conservative | 2.0% | 0/42 | -$40.154 (2000/15m) | -2.0077% |

→ **Even at zero_il_lvr, all cells are negative** because fixed cost (~$0.19) > max fee capture (~$0.04 at 2000/7d/high).

## 3. Why all cells negative (root cause)

For X/USDC (Meteora DLMM):
- **Fee capture TINY**: base_fee_bps=1.5 is low; assumed_volume_pct=0.5% (medium) → fee at 2000/7d is only $0.0000015 × 1000 = $0.0015
- **Cost NON-NEGLIGIBLE**: round-trip tx fees + setup cost = $0.19 minimum
- **IL/LVR ALSO NON-NEGLIGIBLE**: even 0.1% IL = $2 on $2000

→ **Meteora DLMM X/USDC pool at small notionals + tight fees + high fixed cost = structurally negative EV for retail-scale single-position LP**.

## 4. Confidence + honest reporting

- per-row confidence = 0.4 (heuristic-based)
- fee capture = heuristic (mark `heuristic: true`)
- IL/LVR = scenario-based proxy (no actual realized data)
- cost = heuristic on SOL price + priority fee
- **Missing fields explicitly marked**: actual on-chain volume, actual realized IL, actual slippage, real SOL price, real priority fee
- 21/168 cells are "near break-even" (within ±0.05%); all are slightly negative

## 5. 关键 honest finding

- **partial EV preview for X/USDC at retail notionals (10-2000 USD) is NEGATIVE across all scenarios**
- Best case is -$0.154 (-0.0077%) at 2000/15m
- Real EV may differ if (a) actual volume is much higher, (b) max_fee_bps kicks in, (c) zero_il_lvr is unrealistic

## 6. 不在本阶段做

- ❌ 不 fill missing data with zero (we use scenario-based proxies for missing data)
- ❌ 不 fake data
- ❌ 不代表 SOL/USDC (no_quote_data)
- ❌ 不接 wallet / 不读 keypair
- ❌ 不构造 transaction
- ❌ 不修改 EVM executor v2

## 7. 安全断言

```text
this_stage_only_ev_computation = true
heuristic_marked = true
negative_ev_honestly_reported = true
solana_wallet_or_keypair_touched = false
can_run_probe_now = false
v2_line_count_unchanged = true (992)
```

## 8. 下一阶段

进入 Stage H — 10/20U preflight implication: 评估 partial EV 是否值得进入 10/20U probe preflight design.
