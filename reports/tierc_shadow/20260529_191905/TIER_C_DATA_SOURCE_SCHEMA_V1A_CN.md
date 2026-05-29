# Tier C Data Source Schema V1A

新增 research-only 表：`tierc_market_quality_enrichment_v1`、`tierc_exit_depth_estimates_v1`、`tierc_holder_concentration_v1`。

## tierc_market_quality_enrichment_v1
- run_id
- pool_id
- token_pair
- buyers_24h
- sellers_24h
- buy_count_24h
- sell_count_24h
- unique_traders_24h
- trader_concentration_status
- data_source
- data_quality_status
- created_at

## tierc_exit_depth_estimates_v1
- run_id
- pool_id
- token_pair
- route_available
- exit_depth_usd
- slippage_10usd
- slippage_20usd
- slippage_50usd
- max_safe_position_usd
- estimate_method
- data_quality_status
- created_at

## tierc_holder_concentration_v1
- run_id
- pool_id
- token_address
- token_symbol
- top10_holder_pct
- holder_source
- data_quality_status
- created_at
