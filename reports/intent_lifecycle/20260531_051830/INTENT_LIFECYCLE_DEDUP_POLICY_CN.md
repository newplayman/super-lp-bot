# INTENT_LIFECYCLE_DEDUP_POLICY_CN

- `pool_time_bucket_15m` raw=36146 deduped=2448 compression_ratio=14.765522875816993 duplicate_risk=medium avoids_duplication=yes recommended=no
- `pool_time_bucket_1h` raw=36146 deduped=623 compression_ratio=58.01926163723917 duplicate_risk=low avoids_duplication=yes recommended=yes
- `pool_score_event` raw=36146 deduped=9 compression_ratio=4016.222222222222 duplicate_risk=medium avoids_duplication=no recommended=no
- `position_reuse_session` raw=36146 deduped=185 compression_ratio=195.38378378378377 duplicate_risk=high avoids_duplication=no recommended=no

- primary dedup policy: `pool_time_bucket_1h`
