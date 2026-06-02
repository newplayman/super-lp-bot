# selected_pool_count = 0 根因审计

## 结论

当前能确认的事实是：

- `checkpoint/state.json` 里的 `selected_pool_count = 8`
- `logs/run.log` 已经扫描到第 33 / 40 个 pool-window 目标
- `final/FINAL_VERDICT.json` 的 `selected_pool_count = 0` 是旧文件，不是当前运行写出的最终结果

因此，`selected_pool_count = 0` 的根因不是输入池文件缺失，也不是当前 run 读不到选池。
它是一个**旧 final 收口文件被保留在 run 目录中**的问题。

## root_cause 枚举

- root_cause: `unknown`

## 说明

如果只看当前 run 的活跃状态，`selected_pool_count` 实际上是 8。
所以这个 `0` 不能被当成当前运行的真实输出。
