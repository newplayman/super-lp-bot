# Recent Position Mark Coverage

- recent windows are measured relative to the latest `tick_time` present in each horizon, not wall-clock now.

| Horizon window | selected samples | position_id present rate % | future position mark coverage % | pool_mark_only rate % | stale/invalid rate % |
| --- | ---: | ---: | ---: | ---: | ---: |
| recent_6h | 1434 | 100.000 | 60.251 | 39.749 | 39.749 |
| recent_24h | 3576 | 100.000 | 26.426 | 73.574 | 73.574 |

## Freshness Judgment

- `6h`: future_position_mark_coverage=60.251%, pool_mark_only_rate=39.749% -> current pipeline still lacks position-level future marks
- `24h`: future_position_mark_coverage=26.426%, pool_mark_only_rate=73.574% -> current pipeline still lacks position-level future marks

## Interpretation

- 这不是纯历史样本问题。最近样本里 `position_id` 已经齐全，但 target-time 之后的 `position_mark` 仍明显不足。
- 因此当前主问题更接近 mark 产出/选择语义，而不是旧样本 lineage 恢复不全。
