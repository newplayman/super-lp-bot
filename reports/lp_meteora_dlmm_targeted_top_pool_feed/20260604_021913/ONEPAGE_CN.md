# Meteora Targeted Top Pool Feed Expansion — One-Page Summary

- stage: `LP_METEORA_DLMM_TARGETED_TOP_POOL_FEED_EXPANSION_V1`
- run_id: `20260604_021913`
- branch: `feat/supabase-postgres-deployment`
- head_before: `852c976`

## 关键结果

```text
status                              = WARN
candidate_raw_count                 = 60
verified_pool_count                 = 56
sdk_decode_success_count            = 56
quote_ready_pool_count              = 27   (上一轮 0 → 本轮 27)
survival_ev_model_ran               = True
row_count                           = 4536
positive_zero_il_lvr_count          = 15
positive_optimistic_count           = 0
positive_realistic_count            = 0
positive_conservative_count         = 0
near_break_even_count               = 19
high_fee_quote_ready_count          = 4
best_pool                           = CnK82s8exdsK (three/SOL, base=100bps)
best_pair                           = FeMbDo/So1111
best_notional                       = 2000
best_hold_window                    = 7d
best_scenario                       = zero_il_lvr
best_net_ev_proxy_usd               = +0.544
best_net_ev_proxy_pct               = +0.0272%
can_run_probe_now                   = False
solana_wallet_or_keypair_touched    = False
transaction_sent                    = False
edge_proven                         = no
tiny_canary_allowed                 = no
recommended_next_stage              = LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1
v2_line_count                       = 992 (unchanged)
```

## 关键 finding

本轮 V8 走通了 targeted feed + 真实 quote path (V7 阻断的 0 quote 在 27 池上被打破)。**但是**:

1. **15 positive cells 全部在 zero_il_lvr scenario + 7d hold + >=500 USD notional** — optimistic/realistic/conservative 全部 0 positive
2. **Best cell +$0.544** 在 2000 USD / 7d / zero_il_lvr (三池并列: CnK82s8 three/SOL, 9bL8Pp GACHA/SOL, HuPRxa MET/USDC, 全部 base=100bps)
3. **Heuristic 0.5%/day turnover 比 observed 10/20u single-swap fee 推导的 0.005%/day 高 100×** — EV 边界 100× overestimated
4. **All best cells are memecoin pools** (three, GACHA, MET) — IL risk 极高

## 决定

recommended_next_stage = `LP_ORCA_WHIRLPOOL_READONLY_CONNECTOR_V1`

理由:
- Meteora DLMM 零售 10–2000 USD LP 在 V1–V8 多个 stage 验证 negative
- V8 走通了 path (targeted feed → 27 quote-ready) — 不是 path 失败, 是协议失败
- Orca Whirlpool 是不同 AMM 协议 (Concentrated Liquidity, V3 类), IL 行为不同
- 下一轮应独立探索 Orca, 而非重复 Meteora

## 不做什么 (硬边界)

- ❌ 不 instantiate Keypair
- ❌ 不构造 transaction
- ❌ 不 swap / open_lp / close_lp / collect_fee
- ❌ 不 paid RPC (public RPC 已够用)
- ❌ 不接 wallet
- ❌ 不 modify EVM executor v2
- ❌ 不 set can_run_probe_now = true
- ❌ 不 set tiny_canary_allowed = yes
- ❌ 不进 10/20U probe preflight (positive_realistic=0)
