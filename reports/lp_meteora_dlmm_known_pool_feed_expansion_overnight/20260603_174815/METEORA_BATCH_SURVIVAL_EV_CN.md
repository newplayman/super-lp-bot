# Meteora Batch Survival EV Preview — Stage J

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`

## 0. 关键结果

```text
row_count                      = 2688
pool_count                     = 16
positive_zero_il_lvr_count     = 0
positive_optimistic_count      = 0
positive_realistic_count       = 0
positive_conservative_count    = 0
near_break_even_count          = 1344
best_pool                      = H9b4sPAeiyN8DEcWa6MG2kvxqmCqBEpxmexwCh84jg4H
best_pair                      = Axhcwf/EPjFWd
best_notional                  = 2000
best_hold_window               = 15m
best_scenario                  = zero_il_lvr
best_net_ev_proxy_usd          = -0.15338
```

## 1. Model (heuristic; same as V8)

For each (pool, notional, hold, scenario):

```
gross_fee_usd      = notional * 0.005 (medium turnover) * (base_fee_bps / 10000)
il_lvr_cost_usd    = notional * IL_LVR_PCT[scenario]
total_cost_usd     = realistic_solana_net_cost (~0.156)
net_ev_usd         = gross_fee - il_lvr - cost
```

Where IL_LVR_PCT = {zero_il_lvr: 0, optimistic: 0.001, realistic: 0.005, conservative: 0.020}.

## 2. Honest gap (heuristic-marked on every row)

- 实际 on-chain volume unknown → 0.5% turnover is heuristic
- 实际 IL/LVR unknown → IL/LVR is heuristic
- 实际 Solana priority fee unknown → cost uses 10k microlamports
- 实际 rent unknown → cost uses 0.00218928 SOL
- 实际 SOL price unknown → cost uses 130 USD/SOL

## 3. 安全断言

```text
this_stage_only_heuristic       = true
heuristic_marked_on_all_rows    = true
solana_wallet_or_keypair_touched = false
can_run_probe_now                = false
```

## 4. 下一阶段

进入 Stage K — candidate decision。
