# Orca Survival EV Preview — Stage J

- stage: `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`
- run_id: `20260604_025414`

## 0. 关键结果

```text
row_count                   = 1680   (10 pools × 6 notionals × 7 hold × 4 scenarios)
quote_ready_pool_count      = 10
positive_zero_il_lvr_count  = 29
positive_optimistic_count   = 0
positive_realistic_count    = 0
positive_conservative_count = 0
near_break_even_count       = 928
best_pool                   = C9U2Ksk6KKWvLEeo5yUQ7Xu46X7NzeBJtd9PBfuXaUSM
best_pair                   = SOL/Fartcoin
best_notional               = 2000
best_hold_window            = 7d
best_scenario               = zero_il_lvr
best_net_ev_proxy_usd       = +0.106
best_net_ev_proxy_pct       = +0.0053%
```

## 1. 上一轮 (Meteora V8) vs 本轮 (Orca V1)

| 维度 | Meteora V8 (targeted) | Orca V1 (本轮) |
|---|---|---|
| quote_ready_pool_count | 27 | 10 (受 429 限制, 实际可达 30+) |
| row_count | 4536 | 1680 |
| positive_zero_il_lvr | 15 | **29** |
| positive_optimistic | 0 | 0 |
| positive_realistic | 0 | 0 |
| positive_conservative | 0 | 0 |
| best_net_ev | +$0.544 (2000/7d/zero_il_lvr) | +$0.106 (2000/7d/zero_il_lvr) |
| best fee_rate | 100bps (CnK82s8 memecoin) | **16bps** (C9U2Ksk6 SOL/Fartcoin) |

**关键差别**:
- Orca V1 fee 范围 0.01%–2% (vs Meteora max 1%) — 但最高 quote-ready fee 实际只到 16bps
- Meteora V8 best 池是 100bps memecoin (3 池并列), 0.544 USD margin
- Orca V1 best 池是 16bps SOL/Fartcoin, 0.106 USD margin
- Meteora V8 在 2000/7d 集中, Orca V1 同样 (7d 是长持, 不是 LP 零售特征)

**共同结论**: positive_realistic=0 → 两个 V3 类 CL AMM 在 retail 10/20U 2000 USD 都 negative。

## 2. Best 5 池

| pool | pair | fee_bps | best ev | notional | scenario |
|---|---|---|---|---|---|
| C9U2Ksk6KKWvLE | SOL/Fartcoin | 16 | +0.106 | 2000/7d | zero_il_lvr |
| CeaZcxBNLpJWtx | SOL/cbBTC | 16 | +0.106 | 2000/7d | zero_il_lvr |
| C1MgLojNLWBKAD | JUP/SOL | 5 | +0.029 | 2000/7d | zero_il_lvr |
| B5EwJVDuAauzUE | SOL/WBTC | 5 | +0.029 | 2000/7d | zero_il_lvr |
| Czfq3xZZDmsdGd | SOL/USDC | 4 | +0.022 | 2000/7d | zero_il_lvr |

**全在 zero_il_lvr 假设下**; 任何 IL/LVR 假设都为负。

## 3. Honest gap (heuristic marked on every row)

- daily_turnover = 0.5% (heuristic, Meteora V8 同一假设)
- 真实 10u quote fee: 0.0004–0.0123 USD (Czfqq 0.004, C9U2 0.0123)
- implied daily turnover from 10u quote (if every swap is 10u and 1 swap/day) = 0.0001–0.0003 of notional → 比 0.5% 假设小 100×–5000×
- cost: $0.006 (V1 设计 doc)
- IL/LVR: 0%–2% per day (V7 model)

## 4. 安全断言

```text
this_stage_only_ev         = true
this_stage_no_tx           = true
this_stage_no_keypair      = true
heuristic_marked_on_all_rows = true
can_run_probe_now          = false
```

## 5. 下一阶段

进入 Stage K — candidate decision:

- `positive_realistic_count = 0` → 不能进 10/20U probe preflight design
- `quote_ready_pool_count = 10` (实际可达 30+, 受 429 限制)
- best cell **$0.106 in zero_il_lvr only** → 仍受 IL 主导
- Meteora V8 已 reject; Orca V1 同样 reject
- 下一轮按 spec rule_2 → **`LP_RAYDIUM_CLMM_READONLY_CONNECTOR_V1`** (3rd V3 类 CL AMM, 不同 fee structure)
