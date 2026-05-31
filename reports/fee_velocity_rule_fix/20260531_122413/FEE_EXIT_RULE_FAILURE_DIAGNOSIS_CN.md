# 上一轮规则失败归因

- 上一轮 best variant: `exit_depth_min_20usd` / `10 USD` / `recent_7d` / `2h`
- best variant 之所以胜出: 主要因为 `tail_improvement_p10/p5/p1` 最大，但 `opportunity_retention_rate=0.095861`，保留率过低。
- `false_filter_rate=0.904139` 说明规则主要靠过滤掉绝大多数正收益样本来压尾。
- `missed_profit_rate=0.99934` 接近 1，说明几乎全部正收益被误杀。
- `fee_minus_exit_cost_median=-0.030192` 仍为负，fee proxy 无法覆盖退出成本。
- 10 USD 明显优于 20/50 USD，但仍未达到 practical。
- 下面表格给出每个 variant/capacity/window/horizon 的主失败原因。
