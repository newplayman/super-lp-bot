# Fixed Horizon OOS Trend

- previous_run_id: `20260530_134500`
- current_run_id: `20260530_140551`
- trend_status: `FLAT`

对比结果：

- `position_count_6h`: `68 -> 68`，delta `0`
- `position_count_12h`: `68 -> 68`，delta `0`
- `position_count_24h`: `68 -> 68`，delta `0`
- `completed_6h_count`: `42 -> 42`，delta `0`
- `completed_12h_count`: `40 -> 40`，delta `0`
- `completed_24h_count`: `8 -> 8`，delta `0`
- `recent_24h new_position_count`: `6 -> 6`，delta `0`
- `recent_48h new_position_count`: `12 -> 12`，delta `0`

proof 指标变化：

- `6h p10/p5/p1`: 无变化
- `12h p10/p5/p1`: 无变化
- `24h p10/p5/p1`: 无变化
- `top20_vs_bottom20_signal`: 无变化
- `sample_sufficiency`: 仍为 `INSUFFICIENT`

结论：

- 这轮不是退化，但也没有新增样本推进主结论。
- 当前 fixed-horizon 仍处于 `collecting_oos`，只能继续累积。

