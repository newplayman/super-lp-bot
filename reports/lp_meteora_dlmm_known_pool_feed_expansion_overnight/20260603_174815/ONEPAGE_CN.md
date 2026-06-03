# Meteora Known Pool Feed Expansion Overnight — One-Page Summary

- stage: `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_OVERNIGHT_V1`
- run_id: `20260603_174815`
- branch: `feat/supabase-postgres-deployment`
- head_before: `404ddd1`

## 关键结果

```text
status                              = WARN
candidate_raw_count                 = 50
verified_pool_count                 = 16
sdk_decode_success_count            = 16
quote_ready_pool_count              = 0
survival_ev_model_ran               = True
row_count                           = 2688
positive_zero_il_lvr_count          = 0
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 1344
best_pool                           = H9b4sPAeiyN8DEcWa6MG2kvxqmCqBEpxmexwCh84jg4H
best_pair                           = Axhcwf/EPjFWd
best_notional                       = 2000
best_hold_window                    = 15m
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = -0.15338
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT
v2_line_count                       = 992 (unchanged)
```

## 关键 finding

扩大 known pool feed 后扫描了 50 个 candidate pool；16 个通过链上 owner = Meteora DLMM program 验证；16 个 SDK decode 成功；0 个 quote 成功（V1: 1 direction only）。

Survival EV model 在 quote-ready pools 上跑完整 grid (6 notionals × 7 hold × 4 scenario = 168 cells per pool)，结果：
- realistic scenario positive: 0 cells
- zero_il_lvr positive: 0 cells
- best: -0.15338 USD at 2000/15m/zero_il_lvr

## 决定

recommended_next_stage = `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_REPEAT`

## 不做什么（硬边界）

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
