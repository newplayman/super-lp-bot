# Intent To Position Conversion Audit

- `recent_24h` trace=`28052`
- `recent_24h selected=`5756
- `recent_24h intent_open=`5619
- `recent_24h distinct pools in intent_open=`4`
- `recent_24h unique position_id in intent_open=`10`
- `recent_24h positions join success=`5619`

关键证据：

- `intent_open_reason_distribution` 显示：
  - `reuse_shadow_position = 5613`
  - `open_shadow_position = 6`
- 所以 `intent_open` 并不等价于 “应该新建 position”。
- 当前 24h 的 5619 条 `intent_open` 里，几乎全部是对少数已存在 shadow position 的复用。
- `repeated_same_pool_same_tick_count = 0`，不是同 tick 重复刷噪音。
- 但 `repeated_same_intended_position_count = 5609`，说明大量 intent 行是跨 tick 对同一批 position 的持续复用。

判断：

- `5607 intent_open -> 6 new positions` 在当前语义下是可解释的，不是直接的 writer failure。
- root cause 更接近：
  - `POSITION_REUSE_EXPECTED`
  - `INTENT_OPEN_SEMANTIC_MISLABELED`

排除项：

- `POSITION_WRITER_NOT_TRIGGERED`: 否。因为 `position_id_present_count = 5619`，且都能 join 到 `positions`
- `INTENT_OPEN_DUPLICATE_TRACE_NOISE`: 否。不是同 tick 重复噪音，而是跨 tick 重复复用
- `MAX_POSITION_LIMIT_EXPECTED`: 当前没有直接证据
- `POST_INTENT_RISK_GATE_BLOCK`: 当前没有直接证据

