# CLEAN_POSITION_GENERATION_AUDIT_CN

- latest 24h new_positions_count=4, reused_position_count=8
- latest 24h distinct_position_id_from_intent_open=8, distinct_pool_id_from_intent_open=4
- latest 24h entry_trusted positions=2
- latest 24h future_position_mark: 6h=1, 12h=0, 24h=0

## 结论
- 是否真的没有新 position: 否，但新增很少
- 是否大量 intent_open 都是 position reuse: 是
- 是否 reuse 机制导致样本自然增长很慢: 部分是
- clean fixed-horizon 是否需要新 position 但当前 shadow 主要在复用旧 position: 是
- 继续等待是否能自然增加 clean samples: 较慢，单靠等待不足
