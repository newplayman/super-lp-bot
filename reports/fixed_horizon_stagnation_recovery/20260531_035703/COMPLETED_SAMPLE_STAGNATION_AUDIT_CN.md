# COMPLETED_SAMPLE_STAGNATION_AUDIT_CN

- latest run_id=20260530_140551 created_at=2026-05-30 14:06:54.987561+00:00
- latest completed: 6h=42, 12h=40, 24h=8
- latest invalid: 6h=26, 12h=28, 24h=60
- latest no_future_mark: 6h=26, 12h=28, 24h=60
- latest terminal_before_target: 6h=0, 12h=0, 24h=0
- latest pool_mark_only: 6h=0, 12h=0, 24h=0
- recent positions table terminal_before_24h (72h window)=19

## 结论
- completed 不增长是否因 no new positions: 部分是
- 还是有 positions 但 no future marks: 是，24h 与 12h 覆盖明显不足
- 还是 positions terminal before target: 是，但在 canonical proof 中被 no_future_mark 吞并/错记
- 还是 strict proof 排除了大量 pool_mark_only: 当前 v2 strict 下不明显
- 还是 materializer run 口径不同: 存在 terminal/no_future_mark 语义错位，但 run 之间 completed 仍持平
