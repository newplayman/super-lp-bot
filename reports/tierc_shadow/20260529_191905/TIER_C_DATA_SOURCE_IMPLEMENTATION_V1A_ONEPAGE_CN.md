# Tier C Data Source Implementation V1A Onepage

- status: `WARN`
- stage: `TIER_C_DATA_SOURCE_IMPLEMENTATION_V1A`
- candidate_count: `15`
- trader_proxy_coverage: `14`
- exit_depth_coverage: `14`
- holder_coverage: `1`
- stability_coverage: `3`
- data_ready_count: `0`
- micro_candidate_research_only_count: `0`
- shadow_only_data_ready_count: `0`
- watch_count: `8`
- reject_count: `7`
- top_missing_fields: `['top10_holder_pct', 'unique_traders', 'trader_concentration', 'tvl_change_1h']`
- edge_proven: `no`
- tiny_canary_candidate: `no`
- tiny_canary_allowed: `no`
- recommended_next_stage: `TIER_C_DATA_SOURCE_IMPLEMENTATION_REPEAT`

说明：V1A 已显著补齐 trader proxy / exit depth / short-window stability，但 holder concentration 覆盖几乎为空，当前 `data_ready_count=0`，所以不能进入 V2 position OOS。
