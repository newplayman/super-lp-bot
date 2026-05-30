# Tier B Watch Data Gap Stratification

- total_watch_count: 77
- one_field_away_count: 3
- two_fields_away_count: 13
- hard_risk_visible_count: 59
- data_fix_priority_counts: {'HIGH': 3, 'MEDIUM': 13, 'LOW': 2, 'DO_NOT_FIX': 59}
- likely_next_status_if_fixed_counts: {'SHADOW_ONLY_DATA_READY': 16, 'WATCH_DATA_MISSING': 2, 'REJECT': 59}
- most_common_missing_fields: trader=76, stability=66, holder=8

高优先近可用池只有 3 个，分别是 `cbBTC/USDC`、`cbBTC / USDC 0.05%`、`WETH / USDC 0.01%`。其余大部分 WATCH 池在完整补数前已经暴露硬风险，不值得全量重扫。
