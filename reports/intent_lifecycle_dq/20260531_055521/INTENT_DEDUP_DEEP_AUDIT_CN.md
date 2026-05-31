# INTENT_DEDUP_DEEP_AUDIT_CN

- `pool_time_bucket_15m` deduped=2446 compression=14.775960752248569 max_source_trace_count=16 top_pool_share=0.25756336876533115 top_position_share=0.15699100572363042 status=WARN bias=under_compress_repeat_ticks
- `pool_time_bucket_1h` deduped=622 compression=58.10610932475884 max_source_trace_count=60 top_pool_share=0.25562700964630225 top_position_share=0.15434083601286175 status=FAIL bias=moderate_time_bucket_bias
- `pool_time_bucket_4h` deduped=163 compression=221.73006134969324 max_source_trace_count=240 top_pool_share=0.25153374233128833 top_position_share=0.147239263803681 status=FAIL bias=over_compress_multi-intent-windows
- `pool_score_event` deduped=9 compression=4015.777777777778 max_source_trace_count=9336 top_pool_share=0.2222222222222222 top_position_share=0.2222222222222222 status=FAIL bias=score-band-collapse
- `position_reuse_session` deduped=184 compression=196.42391304347825 max_source_trace_count=360 top_pool_share=0.27717391304347827 top_position_share=0.1358695652173913 status=FAIL bias=position-reuse-path-dependence
