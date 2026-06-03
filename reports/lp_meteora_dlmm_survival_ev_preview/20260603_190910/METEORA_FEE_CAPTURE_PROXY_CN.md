# Meteora Fee Capture Proxy — Stage E

- stage: `LP_METEORA_DLMM_SURVIVAL_EV_PREVIEW_V1`
- run_id: `20260603_190910`
- scope: `partial_pool2_only (X/USDC)`

## 0. 关键结果

```text
rows                         = 126  (6 notionals × 7 hold_windows × 3 fee_scenarios)
pool                         = 9DiruRpjnAnzhn6ts5HGLouHtJrT1JGsPbXNYCrFz2ad (X/USDC)
all_rows_heuristic_marked    = true
all_rows_invalid_reason_set  = true (no actual on-chain volume; scenario-based proxy; mark heuristic)
data_confidence              = 0.3 (low; scenario-based; not measured)
```

## 1. fee_scenario 与 assumed_volume_turnover_pct

| fee_scenario | turnover_pct (per hold window) | effective_fee_bps | notes |
|---|---|---|---|
| low | 0.001 (0.1% of notional) | 1.5 (base_fee) | pessimistic; pool has very low volume |
| medium | 0.005 (0.5% of notional) | 1.5 (base_fee) | realistic default; aligns with prior V8 |
| high | 0.02 (2% of notional) | 5.0 (max_fee mid-range) | optimistic; max_fee kicks in under volatility |

Per V4 fee snapshot: base_fee_bps=1.5, max_fee_bps=10. Meteora DLMM fee is `base_fee_bps + dynamic_volatility_fee_bps`; without `volatility_accumulator` (not exposed by SDK v1.9.10), the high scenario uses 5 bps (mid-range between base 1.5 and max 10).

## 2. Per-row formula (heuristic)

```
assumed_volume_usd        = notional_usd × turnover_pct
estimated_fee_capture_usd = assumed_volume_usd × (fee_bps / 10000)
```

Examples (medium fee_scenario, 15m hold):

| notional | assumed_volume_usd | fee_capture_usd |
|---|---|---|
| 10 | 0.05 | 7.5e-06 |
| 100 | 0.50 | 7.5e-05 |
| 1000 | 5.00 | 7.5e-04 |
| 2000 | 10.00 | 1.5e-03 |

The fee capture is *very* small at retail notionals (10–2000 USD) because the pool has no measured on-chain volume, and we apply a conservative turnover. The prior V8 (20260603_153736) used identical numbers — see `meteora_fee_capture_proxy.csv` for full 126 rows.

## 3. Why heuristic (not measured)

- We have not pulled actual on-chain swap volume from Meteora for this pool. SDK v1.9.10 does not expose a "24h volume" field on the LbPair account.
- CoinGecko / Birdeye / DexScreener are external paid sources (per spec, no paid RPC; no external volume API assumed in this stage).
- Per spec hard rule: missing data must be marked `missing` or `heuristic`, not 0. All 126 rows have `heuristic=true` and `invalid_reason` non-empty.

## 4. Honest gap

- 实际 on-chain volume of X/USDC pool is **unknown** to this model.
- Real EV could be 10× higher if pool volume is 10× the optimistic scenario. This is exactly what `LP_METEORA_DLMM_KNOWN_POOL_FEED_EXPANSION_V1` would test: find pools with known high 24h volume (e.g., from Meteora UI top-pools list) and recompute EV with the new pool.

## 5. 不在本阶段做

- ❌ 不 instantiate Keypair
- ❌ 不调 swapQuote (V6 already did; reused)
- ❌ 不调 GPA
- ❌ 不读 keypair
- ❌ 不 fake volume from external source
- ❌ 不 modify EVM executor v2

## 6. 安全断言

```text
this_stage_only_heuristic     = true
heuristic_marked_on_all_rows  = true
solana_wallet_or_keypair_touched = false
can_run_probe_now             = false
v2_line_count_unchanged       = true (992)
```

## 7. 下一阶段

进入 Stage F — Solana cost model (3 scenarios: low/realistic/conservative).
