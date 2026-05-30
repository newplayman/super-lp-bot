# Future Mark Coverage Audit

- `6h` matured=`11`, future position mark=`11`, pool mark only=`0`, terminal before target=`1`, no mark=`0`
- `12h` matured=`10`, future position mark=`10`, pool mark only=`0`, terminal before target=`2`, no mark=`0`
- `24h` matured=`6`, future position mark=`0`, pool mark only=`6`, terminal before target=`6`, no mark=`0`

关键判断：

- `6h/12h` 覆盖链本身是通的，成熟样本都拿到了 position-level future marks。
- 真正的问题集中在 `24h`：
  - 已成熟的 `6` 个 position 全部在 target 前 terminal
  - target 时刻仍能看到 pool-level marks
  - 但 position-level future mark 不存在

所以 24h coverage 的主因不是 “mark worker 全局坏了”，而是：

- `POSITION_TERMINAL_BEFORE_TARGET`
- `POOL_MARK_ONLY`

补充：

- 对 recent 还未成熟的 position，`HORIZON_NOT_MATURE` 仍然存在，但不是当前 24h matured 样本为 0 的唯一解释。

