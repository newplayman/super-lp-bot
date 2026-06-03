# Meteora Survival EV Preview — One-Page Summary

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- branch: `feat/supabase-postgres-deployment`
- head_before: `3065d23`

## 关键结果（一页纸）

```text
status                              = WARN
scope                               = partial_pool2_only (X/USDC only)
included_pool_count                 = 1  (X/USDC pool 2)
excluded_pool_count                 = 1  (SOL/USDC pool 1; reason=no_quote_data)
survival_ev_model_ran               = true
row_count                           = 168 (6 notionals × 7 hold_windows × 4 scenarios)
positive_zero_il_lvr_count          = 0
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count (<0, >-0.5)   = 84
best_notional                       = 2000
best_hold_window                    = 15m
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = -0.154 (still negative)
best_net_ev_proxy_pct               = -0.0077%
x_usdc_preflight_candidate          = false
can_run_probe_now                   = false
solana_wallet_or_keypair_touched    = false
transaction_sent                    = false
edge_proven                         = "no"
tiny_canary_allowed                 = "no"
v2_line_count_unchanged             = true (992)
recommended_next_stage              = LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1
```

## 关键 finding

V8 partial survival EV preview for X/USDC at 10–2000 USD notionals is **structurally negative**. 168/168 cells are negative; even the best case (2000 notional + 15m + zero_il_lvr) is -$0.154. Root cause: low base fee (1.5%) + low assumed volume + high fixed cost (~$0.16 per position). The model is heuristic-based and missing actual on-chain volume / realized IL — but the order-of-magnitude conclusion is the same: at retail notionals, Meteora DLMM X/USDC single-position LP cannot recover the fixed cost.

## 决定

- **NOT** proceed to 10/20U X/USDC probe (would be wasted work; all 24 cells negative)
- **NOT** set up paid RPC for SOL/USDC yet (deferrable; X/USDC alone is insufficient)
- **NOT** fix-repeat the survival EV preview (model is correct; this re-run reproduces prior run 20260603_153736)
- **NOT** stop LP research entirely (read-only path is productive)
- **DO** expand known pool feed: include 5–10 Meteora DLMM pools with higher base fee / measured volume, or expand to other AMM protocols (Raydium CLMM, Orca Whirlpools)
- **DO** re-run survival EV preview with expanded feed to find pools with positive EV

## 不做什么（硬边界）

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes

## 下一阶段

`LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` (read-only; public RPC; no probe).
