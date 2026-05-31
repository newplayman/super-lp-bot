# P0 下一阶段任务规格

## 任务名

`RISK_AWARE_SHORT_HOLD_COUNTERFACTUAL_V1`

## 目标

验证短持有 + 风险优先退出是否显著压低尾部损失，而不是先证明 median 变好。

## Proof unit

- `pool_window`
- `intent_window`
- 不再依赖 `position_lifecycle` 作为主证明单位

## Horizons

- `15m`
- `30m`
- `1h`
- `2h`

## Counterfactual 对比

1. `hold_to_horizon`
2. `risk_aware_exit`
3. `no_entry / quarantine`

## 核心指标

- median
- p10
- p5
- p1
- false_exit_rate
- missed_profit
- loss_saved
- fee_proxy_vs_exit_cost
- worst_pool_contribution
- worst_event_contribution

## 判定原则

1. 先看尾部是否改善。
2. 只读比较，不下单。
3. 任何结论都不能升级为 canary。
4. 若 `p10 / p5 / p1` 没改善，即使 median 上升也不能算通过。

## 数据依赖

- pool snapshot
- short-window price / volume
- exit depth estimate
- risk event labels
- fee proxy
- future mark / intent window alignment

## 预期输出

- counterfactual result table
- tail comparison summary
- false exit and missed profit balance
- worst pool / worst event attribution

## 安全边界

- `tiny_canary_allowed = no`
- no live / paper / wallet / tx / bridge
- no production table writes
