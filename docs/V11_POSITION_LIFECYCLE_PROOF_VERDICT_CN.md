# V11 Position Lifecycle Proof Verdict

- decision_trace-level proof 已废弃为 primary proof。
- position_lifecycle 是唯一主证明单位。
- current_full_strategy = FAIL。
- 失败原因：position-level tail 不过线。
- tiny_canary_allowed = no。

## Tail Metrics

- 24h: p10 = -2.242177, p5 = -2.454014, p1 = -2.537614
- 6h: p10 = -2.356639, p5 = -2.531888, p1 = -3.408496

## Notes

- 6h/24h ranking direction can still be better at position level.
- That is not enough. Current strategy remains FAIL until the tail is acceptable at position level.
