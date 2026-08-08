# LP Cost Sensitivity — Base vetted pool

As of analysis: `2026-08-08T17:25:41.290916+00:00` (historical inputs; no live/network calls)
Pool: `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59` · aerodrome-slipstream WETH-USDC
Horizon for MinEconomicPosition: 720h; conservative fee APR 20.1462%; reward APR 67.6834% × haircut 0.50.

LVR and exit-latency are model estimates. Active liquidity is a historical notional proxy from the cited depth artifact; gas is a historical replay observation.

| size U | round-trip U | fixed cost U | break-even h | MinEconomicPosition U | NetCover 30d | abs-profit gate | runtime cap U |
|---:|---:|---:|---:|---:|---:|:---:|---:|
| 25 | 0.042263 | 0.121763 | 104.36 | 33.83 | 2.837 | SKIP | 500.00 |
| 50 | 0.084852 | 0.164352 | 70.43 | 33.83 | 3.157 | PASS | 500.00 |
| 75 | 0.127766 | 0.207266 | 59.21 | 33.83 | 3.279 | PASS | 500.00 |
| 100 | 0.171007 | 0.250507 | 53.67 | 33.83 | 3.343 | PASS | 500.00 |
| 200 | 0.347228 | 0.426728 | 45.72 | 33.83 | 3.439 | PASS | 500.00 |
| 500 | 0.907174 | 0.986674 | 42.28 | 33.83 | 3.482 | PASS | 500.00 |

Sources:
- `reports/lp_pool_resolve_and_rank/run_qualityA/resolve_and_rank.json`
- `reports/lp_quote_depth_curve_fix/20260601_091739/quote_depth_curve_v2_results.csv`
- `reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000/active_liquidity_corrected_replay_matrix.jsonl`
