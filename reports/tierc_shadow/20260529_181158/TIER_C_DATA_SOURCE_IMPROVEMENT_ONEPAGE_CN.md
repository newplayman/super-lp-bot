# Tier C Data Source Improvement Onepage

- status: `WARN`
- stage: `TIER_C_DATA_SOURCE_IMPROVEMENT_V1`
- candidate_count: `15`
- data_ready_count: `0`
- micro_candidate_research_only_count: `0`
- watch_data_missing_count: `8`
- reject_count: `7`
- top_missing_fields: `['buyers_24h', 'sellers_24h', 'buy_count_24h', 'sell_count_24h', 'unique_traders', 'trader_concentration', 'top10_holder_pct', 'exit_depth_usd']`
- recommended_next_stage: `TIER_C_DATA_SOURCE_IMPLEMENTATION`
- edge_proven: `no`
- tiny_canary_candidate: `no`
- tiny_canary_allowed: `no`

结论：当前 15 个候选的主要问题是交易者覆盖、短窗稳定性和 exit depth 数据缺失。先补数据源，再谈下一轮 rediscovery 或 OOS。
