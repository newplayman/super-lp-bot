# Trace Duplication Root Cause

| position_id | pool_id | token_pair | decision_trace_count | selected_trace_count | top20_trace_count | first_trace_time | last_trace_time | open_time | exit_time | trace_span_minutes | repeat_each_scan | multi_horizon_duplicate | multi_score_duplicate | proof_unit_should_be_position_lifecycle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 3490 | 3490 | 3186 | 2026-05-21 04:24:42 UTC | 2026-05-23 18:40:34 UTC | 2026-05-21 03:04:52 UTC | 2026-05-23 18:41:48 UTC | 3735.9 | yes | yes | yes | yes |
| shadow-pos-ec687b2aceeb808a1f6c75ac | 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | base:aerodrome-slipstream:0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59 | 3490 | 3490 | 3259 | 2026-05-21 04:24:42 UTC | 2026-05-23 18:40:34 UTC | 2026-05-21 03:04:52 UTC | 2026-05-23 18:41:48 UTC | 3735.9 | yes | yes | yes | yes |
| shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 3479 | 3479 | 0 | 2026-05-21 06:15:19 UTC | 2026-05-23 20:38:48 UTC | 2026-05-21 06:15:20 UTC | 2026-05-23 20:39:11 UTC | 3743.5 | yes | yes | no | yes |
| shadow-pos-e2deacabdd6dcb7bc764a7bd | 0x9a993fc0eec60faaa0c391ff11b840ce16685150 | base:uniswap-v3-base:0x9a993fc0eec60faaa0c391ff11b840ce16685150 | 3479 | 3479 | 0 | 2026-05-21 06:15:19 UTC | 2026-05-23 20:38:48 UTC | 2026-05-21 06:15:20 UTC | 2026-05-23 20:39:11 UTC | 3743.5 | yes | yes | no | yes |

## Conclusion

- TRACE_DUPLICATION_ARTIFACT = yes
- decision_trace_level_primary_proof = no
- position_level_primary_proof = yes
