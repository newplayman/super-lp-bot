# Recent Fixed Horizon OOS

- run_id: 20260529_1230
- proof_unit: position_lifecycle
- hypothesis_type: fixed_horizon_or_no_terminal
- current_full_strategy: FAIL
- tiny_canary_allowed: no

| window | new_position_count | completed_6h_count | completed_24h_count | future_position_mark coverage | entry_trusted rate | median | p10 | p5 | p1 | top20 vs bottom20 signal | tail concentration | sample_sufficiency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| recent 2h | 1 | 0 | 0 | 0.000000 | 0.000000 |  |  |  |  | insufficient | 1.000000 | SAMPLE_INSUFFICIENT |
| recent 4h | 1 | 0 | 0 | 0.000000 | 0.000000 |  |  |  |  | insufficient | 1.000000 | SAMPLE_INSUFFICIENT |
| recent 8h | 2 | 0 | 0 | 0.000000 | 0.000000 |  |  |  |  | insufficient | 0.500000 | SAMPLE_INSUFFICIENT |
| recent 12h | 2 | 0 | 0 | 0.000000 | 0.000000 |  |  |  |  | insufficient | 0.500000 | SAMPLE_INSUFFICIENT |
| recent 24h | 7 | 0 | 0 | 0.000000 | 0.000000 |  |  |  |  | insufficient | 0.714286 | SAMPLE_INSUFFICIENT |

- SAMPLE_INSUFFICIENT means no edge claim and no canary discussion.
