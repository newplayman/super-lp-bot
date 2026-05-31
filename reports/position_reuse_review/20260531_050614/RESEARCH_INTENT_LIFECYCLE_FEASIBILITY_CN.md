# RESEARCH_INTENT_LIFECYCLE_FEASIBILITY_CN

- recent_7d feasibility_status=FEASIBLE unique_intent_count=36178 unique_pool_time_bucket_count=623 unique_intent_lineage_trusted_count=36059

## 结论
- intent lifecycle 是否能成为新的 research-only hypothesis: 可以
- 它有退化成 decision_trace 重复计数的风险。
- 去重必须至少用 pool + time bucket + score event，而不是原始 trace row。
- 还需要 entry/value/future pool mark/lineage trust 字段才能避免旧 duplication 坑。
