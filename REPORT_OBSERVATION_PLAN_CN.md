# Shadow Observation 观察计划

目标不是立即扩大 live，而是先让 `shadow_outcome_labels` 跑出第一批可用样本，再判断策略是否值得 tiny canary。

## 阶段 A: 1h Smoke

观察表：

- `shadow_decision_trace`
- `shadow_position_marks`
- `shadow_outcome_labels`
- `portfolio_snapshots`

观察点：

1. `shadow_outcome_labels` 是否开始产生 `1h` 样本
2. `label=invalid` 比例是否异常高
3. `REPORT_SHADOW_OUTCOMES_CN.md` 是否可正常生成
4. `live_readiness_check.sh` 是否能输出一致的 PASS/WARN/FAIL

## 阶段 B: 6h

观察点：

1. `selected_sample_count` 是否开始积累
2. `realized_sample_count` 是否足够形成初步统计
3. `gas_adjusted_positive_rate` 是否明显高于 50%
4. `high_score_vs_low_score` 是否为 `better`
5. `avg_net_pnl` / `median_net_pnl` 是否为正
6. `p10_net_pnl` 是否仍在可接受阈值内

## 阶段 C: 24h

观察点：

1. 各 horizon 样本是否稳定
2. `invalid_rate` 是否下降到可接受范围
3. 高 score / 高 TVL / 合适 fee tier 的 bucket 是否持续更优
4. 是否仍然是 gas 后正收益，而不是名义正收益

## Tiny Canary 前置条件

只有下面条件同时满足，才考虑一次极小额 canary：

1. VPS readiness = `PASS`
2. `portfolio_snapshots` 连续 30-60 分钟新鲜
3. `stuck / exit_failed / unreconciled timeout = 0`
4. `6h` shadow outcome 至少 `WARN`，不能 `FAIL`
5. 目标 pool 所在 bucket 的 `median_net_pnl >= 0`
6. `high_score_vs_low_score = better`
7. `max_order_usd <= 5~10`

## 如果结果不好

如果 `6h` 或 `24h` 报告显示：

- `avg_net_pnl <= 0`
- `median_net_pnl <= 0`
- `invalid_rate` 过高
- `high_score_vs_low_score != better`

那就不要推进 live，先回到：

1. score 组成
2. pool 过滤条件
3. fee / IL / gas 估算口径
4. shadow candidate 选择逻辑
