# Tier C Hard Risk Gates

- max_single_position_usd: 25
- max_total_tierc_exposure_usd: 100
- max_pool_exposure_pct: 25% of tierc sleeve
- min_exit_depth_usd: 1000
- max_top10_holder_pct: 70%
- max_5m_price_move: 5%
- max_tvl_drop_1h: 25%
- max_volume_collapse: 60% vs trailing baseline
- max_hold_time: 6h
- quarantine conditions: market_quality_missing, holder concentration spike, exit depth failure, abrupt TVL drop, repeated symmetric flow flags

- Tier C does not reuse normal LP risk thresholds.
- Tier C is small-size, short-cycle, strong-exit, strong-isolation only.
- tiny_canary_allowed: no
