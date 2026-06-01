# 为什么放大本金没有救回 EV

核心逻辑：

- 放大本金只能摊薄 `fixed cost`。
- 如果 `variable_edge_rate <= 0`，本金放大不会把负 EV 变成正 EV，反而会按更大的 notional 放大亏损或负 proxy。

本轮证据链已经把这个问题拆干净：

1. `LP_VIRTUAL_NOTIONAL_ECONOMICS_V1` 直接测了 `20 / 100 / 500 / 1000 / 2000U`，没有任何 `positive proxy`。
2. `LP_FEE_VELOCITY_PIPELINE_FIX_REPEAT_V1` 说明即使设定 `fixed_cost = 0`，仍然没有 `positive proxy`。
3. `LP_IL_LVR_PIPELINE_V1` 说明即使设定 `IL/LVR = 0`，仍然没有 `positive proxy`。

因此：

- 问题不是单纯本金太小。
- 当前主问题是 `fee / slippage / exit / capacity / data confidence` 这组因素合并后不支持正 EV。
- `1000 / 2000U` 还会额外受 `capacity` 限制。
- `20 / 100 / 500U` 即便容量勉强可测，仍然被 `fee/成本/置信度` 压成负 proxy。

结论：

- 不能再用 `10U / 20U probe` 继续验证收益。
- 继续 probe 只能验证通道，不会改变当前 economics 已经为负的事实。
