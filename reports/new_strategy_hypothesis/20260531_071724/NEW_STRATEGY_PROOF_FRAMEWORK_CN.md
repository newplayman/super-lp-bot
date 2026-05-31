# 新策略证明框架

## 总目标

本轮不追求证明收益已经成立，而是先证明：在短持有窗口里，风险优先退出是否能显著压低尾部损失。

## P0 证明单位

- `pool_window / intent_window`
- 不再依赖 `position_lifecycle` 作为主证明单位
- Horizons: `15m`, `30m`, `1h`, `2h`

## P0 counterfactual 对照组

1. `hold_to_horizon`
2. `risk_aware_exit`
3. `no_entry / quarantine`

## 主要指标

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

## 解释顺序

1. 先看 p10 / p5 / p1 是否改善。
2. 再看 false_exit_rate 是否可接受。
3. 再看 missed_profit 是否被 tail 改善抵消。
4. median 只作为辅助，不作为优先判定条件。

## 样本门槛

- `position_count < 30`: INSUFFICIENT
- `30 <= position_count < 100`: EARLY
- `100 <= position_count < 300`: PRELIMINARY
- `position_count >= 300`: USABLE

## 抗重复规则

- 每个 `pool_window` 只保留一个 counterfactual 样本。
- 同一池同一窗口重复出现时，以 dedup 后的唯一窗口为准。
- 不能回到旧 decision_trace 的重复计数方式。

## 安全边界

- research-only
- no canary
- no live
- no paper
- no wallet / tx / bridge path changes
- no production table writes
