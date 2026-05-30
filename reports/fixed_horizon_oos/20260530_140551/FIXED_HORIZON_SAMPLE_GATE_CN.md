# Fixed Horizon Sample Gate

整体判断：`INSUFFICIENT`

按 horizon：

- `6h`
  - position_count: `68`
  - completed_count: `42`
  - count_gate: `EARLY`
  - completed_gate: `PASS_MIN_COUNT`
- `12h`
  - position_count: `68`
  - completed_count: `40`
  - count_gate: `EARLY`
  - completed_gate: `PASS_MIN_COUNT`
- `24h`
  - position_count: `68`
  - completed_count: `8`
  - count_gate: `EARLY`
  - completed_gate: `INSUFFICIENT`

hypothesis review 最低要求检查：

- `6h completed >= 100`: `no`
- `12h completed >= 100`: `no`
- `24h completed >= 100`: `no`
- 至少两个 horizon completed >= 100: `no`
- `p10` 不明显危险: `no`（`12h p10 = -7.4966%`）
- `p5` 不危险: `no`（`12h p5 = -7.7325%`）
- 至少两个 horizon `top20_vs_bottom20_signal = better`: `no`
- tail concentration 不由单一 position/pool 主导: `no`（`6h worst_position_contribution = 1.0`, `12h worst_pool_contribution = 0.8215`）

结论：

- 当前不能进入 `FIXED_HORIZON_HYPOTHESIS_REVIEW`
- 当前只能继续 `FIXED_HORIZON_CONTINUE_OOS_ACCUMULATION`

