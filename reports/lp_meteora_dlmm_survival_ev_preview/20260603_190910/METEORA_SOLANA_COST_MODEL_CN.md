# Meteora Solana Cost Model — Stage F

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. 关键结果

```text
rows                = 3  (low / realistic / conservative)
sol_price_used      = 130.0 USD/SOL (heuristic; per V8 prior run)
applies_to_probe    = false  (per spec: probe not allowed)
applies_to_scaled   = true   (model; future notional-scaled probe planning only)
all_rows_heuristic  = true
data_confidence     = 0.5
```

## 1. Per-scenario cost breakdown

| scenario | priority_fee (lamports) | per_tx SOL | per_tx USD | round_trip USD | setup USD | recovery USD | net cost USD |
|---|---|---|---|---|---|---|---|
| low | 1,000 | 6.0e-06 | 0.00078 | 0.00156 | 0.2846 | 0.1326 | ~0.154 |
| realistic | 10,000 | 1.5e-05 | 0.00195 | 0.00390 | 0.2846 | 0.1326 | ~0.156 |
| conservative | 100,000 | 1.05e-04 | 0.01365 | 0.02730 | 0.2846 | 0.1326 | ~0.179 |

Numbers match the prior V8 cost model (20260603_153736) within rounding. The realistic scenario is used as the anchor in the survival EV preview Stage G.

## 2. Cost components (heuristic; per spec)

| component | value | source / formula |
|---|---|---|
| base_fee | 5000 lamports (0.000005 SOL) | Solana network default base fee per signature |
| priority_fee | 1k / 10k / 100k microlamports (per scenario) | network-dependent; scenario ranges |
| rent (token account) | 0.00203928 SOL | Solana mainnet rent-exempt minimum for SPL token account (165 bytes) |
| rent (position account) | 0.00015 SOL | DLMM position account rent; estimate from Meteora SDK |
| setup | 0.00218928 SOL (sum of token + position rent) | one-time per wallet per pool |
| recovery (on close) | ~46.6% of setup | Meteora refunds on close_position for unused lamports |
| net cost per position | setup + 2×tx − recovery | applied per pool per holding period |

> NOTE: SOL price (130 USD) is a heuristic. The actual price at the time of any future probe would replace this. The model is insensitive to ±20% SOL price swings for retail notionals (10–2000 USD), because the cost is dominated by rent (~$0.28 fixed) and tx fees (<$0.03 even in the conservative case).

## 3. Honest gap (must mark heuristic, not 0)

- 实际 Solana priority fee depends on network congestion; this model uses 3 fixed scenarios.
- 实际 rent depends on account size policy; Meteora SDK has a known `getRentCost()` helper not invoked here.
- 实际 SOL price at probe time unknown; could move ±50% before any future probe.
- 实际 tx confirmation time affects priority fee; not modeled.

All these are marked `heuristic=true` in the JSON.

## 4. Why applies_to_probe = false (per spec)

The spec for this stage explicitly states "no probe", "no transaction". The cost model is for **future notional-scaled probe planning** if and when `LP_METEORA_DLMM_10_20U_PROBE_PREFLIGHT_DESIGN_V1` is reached, NOT for this run. The current run is purely read-only analysis; `can_run_probe_now=false` and `tiny_canary_allowed=no`.

## 5. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不 call `Meteora SDK getRentCost()`
- ❌ 不构造 transaction
- ❌ 不 modify EVM executor v2
- ❌ 不 fetch live SOL price (would require paid data source)

## 6. 安全断言

```text
this_stage_only_heuristic     = true
heuristic_marked_on_all_rows  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 7. 下一阶段

进入 Stage G — survival EV preview (X/USDC only; 6 notionals × 7 hold_windows × 4 scenarios = 168 cells).
