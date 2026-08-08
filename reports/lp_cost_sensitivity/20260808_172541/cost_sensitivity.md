# LP Cost Sensitivity — Base vetted pool

As of analysis: `2026-08-08T17:28:42.081253+00:00` (historical inputs; no live/network calls)
Pool: `0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59` · aerodrome-slipstream WETH-USDC
Horizon for MinEconomicPosition: 720h; conservative fee APR 20.1462%; reward APR 67.6834% × haircut 0.50.

LVR and exit-latency are model estimates. Position cap uses a historical active-notional depth proxy; swap math uses price and raw active liquidity decoded from a real Swap event; gas is a historical replay observation.

| size U | round-trip U | fixed cost U | break-even h | MinEconomicPosition U | NetCover 30d | abs-profit gate | runtime cap U |
|---:|---:|---:|---:|---:|---:|:---:|---:|
| 25 | 0.042112 | 0.121612 | 104.23 | 33.82 | 2.838 | SKIP | 500.00 |
| 50 | 0.084246 | 0.163746 | 70.17 | 33.82 | 3.160 | PASS | 500.00 |
| 75 | 0.126404 | 0.205904 | 58.82 | 33.82 | 3.283 | PASS | 500.00 |
| 100 | 0.168585 | 0.248085 | 53.15 | 33.82 | 3.349 | PASS | 500.00 |
| 200 | 0.337541 | 0.417041 | 44.68 | 33.82 | 3.452 | PASS | 500.00 |
| 500 | 0.846632 | 0.926132 | 39.69 | 33.82 | 3.516 | PASS | 500.00 |

Sources:
- `reports/lp_pool_resolve_and_rank/run_qualityA/resolve_and_rank.json`
- `reports/lp_quote_depth_curve_fix/20260601_091739/quote_depth_curve_v2_results.csv`
- `reports/strategy_evidence_r4b_active_liquidity_corrected_replay/20260612_090000/active_liquidity_corrected_replay_matrix.jsonl`
- `reports/strategy_evidence_r4_swap_event_fee_replay/20260611_080000/swap_events_decoded.csv`
