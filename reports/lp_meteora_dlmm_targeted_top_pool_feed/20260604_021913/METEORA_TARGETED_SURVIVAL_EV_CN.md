# Meteora Targeted Survival EV Preview — Stage H

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`

## 0. 关键结果

```text
row_count                   = 4536   (27 pools × 6 notionals × 7 hold × 4 scenarios)
quote_ready_pool_count      = 27
positive_zero_il_lvr_count  = 15
positive_optimistic_count   = 0
positive_realistic_count    = 0
positive_conservative_count = 0
near_break_even_count       = 19
best_pool                   = CnK82s8exdsK (three/SOL, base=100bps, bin_step=80)
best_pair                   = FeMbDo…/So1111…
best_notional               = 2000
best_hold_window            = 7d
best_scenario               = zero_il_lvr
best_net_ev_proxy_usd       = +0.5440
best_net_ev_proxy_pct       = +0.0272
```

## 1. 上一轮 vs 本轮

| 维度 | 上一轮 (16 quote-blocked pools) | 本轮 (27 quote-ready pools) |
|---|---|---|
| row_count | 2688 | 4536 |
| positive_zero_il_lvr | 0 | **15** ✓ |
| positive_optimistic | 0 | 0 |
| positive_realistic | 0 | **0** |
| positive_conservative | 0 | 0 |
| best_net_ev | -$0.153 | **+$0.544** ✓ |
| quote_ready | 0 | 27 |
| candidate base fee range | 0.02–2.5 bps | 20–100 bps |

**结构性突破**:
- 上一轮 best -$0.153 (top 16 池全 reject) → 本轮 best **+$0.544** (15 cells positive in zero_il_lvr only)
- 关键差别: 上一轮无 quote 数据, EV model 无法校准；本轮有 27 个真实 quote, EV 边界更可信

**但**:
- 15 positive **全部** 在 `zero_il_lvr` scenario + 7d hold + >=500 USD
- 0 positive in optimistic/realistic/conservative
- 仍受 IL/LVR 模型误差主导

## 2. 15 positive cells 详情

| pool | pair | base/max bps | notional | hold | scenario | ev_usd |
|---|---|---|---|---|---|---|
| `CnK82s8exdsK` | three/SOL | 100/1000 | 500 | 7d | zero_il_lvr | +0.019 |
| `CnK82s8exdsK` | three/SOL | 100/1000 | 1000 | 7d | zero_il_lvr | +0.194 |
| `CnK82s8exdsK` | three/SOL | 100/1000 | 2000 | 7d | zero_il_lvr | +**0.544** |
| `9bL8Pptpb8M2` | GACHA/SOL | 100/1000 | 500 | 7d | zero_il_lvr | +0.019 |
| `9bL8Pptpb8M2` | GACHA/SOL | 100/1000 | 1000 | 7d | zero_il_lvr | +0.194 |
| `9bL8Pptpb8M2` | GACHA/SOL | 100/1000 | 2000 | 7d | zero_il_lvr | +0.544 |
| `HuPRxaBcjQYr` | MET/USDC | 100/1000 | 500 | 7d | zero_il_lvr | +0.019 |
| `HuPRxaBcjQYr` | MET/USDC | 100/1000 | 1000 | 7d | zero_il_lvr | +0.194 |
| `HuPRxaBcjQYr` | MET/USDC | 100/1000 | 2000 | 7d | zero_il_lvr | +0.544 |
| `9uTgLv3Ya7sr` | three/SOL | 50/1000 | 1000 | 7d | zero_il_lvr | +0.019 |
| `9uTgLv3Ya7sr` | three/SOL | 50/1000 | 2000 | 7d | zero_il_lvr | +0.194 |
| `6qz7THwQvcjF` | BP/USDC | 25/1000 | 2000 | 7d | zero_il_lvr | +0.019 |
| `8eDUNVrNUZ87` | FeMbDo…/So1111 | 25/1000 | 2000 | 7d | zero_il_lvr | +0.019 |
| `8pKt3mAE3KVY` | 33eum8/SOL | 25/1000 | 2000 | 7d | zero_il_lvr | +0.019 |
| `Eqv1tJGkLFeH` | jtojto/USDC | 25/1000 | 2000 | 7d | zero_il_lvr | +0.019 |

## 3. Model breakdown (best cell `CnK82s8exdsK` 2000/7d/zero_il_lvr)

```text
notional             = 2000 USD
hold_window          = 7d = 168h
days                 = 7
base_fee_bps         = 100 (1%)
daily_turnover       = 0.005 (heuristic)
gross_fee_usd        = 2000 * 0.005 * 7 * 0.01 = 0.700
il_lvr_cost_usd      = 2000 * 0 * 7 = 0 (zero_il_lvr scenario)
total_cost_usd       = 0.156 (rent + priority fee)
net_ev_usd           = 0.700 - 0 - 0.156 = +0.544
net_ev_pct           = +0.0272% of notional
```

**Real quote bounds (sanity check)**:
- 10u SOL in: fee = 692,308 lamports ≈ $0.0053 USD (implied turnover = 0.0053 / 10 = 0.0005 of notional for ONE trade; daily turnover is way higher — multiple swaps)
- 20u SOL in: fee = 1,384,616 lamports ≈ $0.0106 USD
- Implied daily turnover if 0.7 USD/7d ≈ 0.1 USD/day from 2000 USD notional = 0.005% of notional per day

→ Heuristic 0.5% turnover is **100× higher** than what 10/20u single quote implies. **EV is structurally overestimated by 100×** when using heuristic turnover vs observed single-quote fee.

## 4. Honest gap (heuristic-marked on every row)

```text
real_observed_fee_per_swap_10u = $0.0053 (for CnK82s8exdsK SOL in)
heuristic_daily_turnover_5pct   = 100x higher than observed single-swap turnover
IL_LVR_unknown                  = all values are heuristic
volume_unknown                  = vol24h from GeckoTerminal is swap VOLUME, not LP fee turnover
rent_8x10k_priority             = fixed cost $0.156 is heuristic
SOL_price                       = 130 USD/SOL assumed
```

The **+0.544 USD best cell** is from a model that assumes 100× higher fee capture than observed. If real capture is closer to the observed quote, all cells are negative.

## 5. 安全断言

```text
this_stage_only_ev         = true
this_stage_no_tx           = true
this_stage_no_keypair      = true
heuristic_marked_on_all_rows = true
can_run_probe_now          = false
```

## 6. 下一阶段

进入 Stage I — candidate decision:

- `positive_realistic_count = 0` → 不能进 10/20U probe preflight design
- `quote_ready_pool_count = 27` (大幅增加 vs 0)
- best cell **in zero_il_lvr only** 且 margin $0.544 在 2000 USD / 7d → IL 主导风险太高
- 按 spec decision rule → **`LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`** (不同 AMM 协议, 集中流动性, IL 行为不同)
