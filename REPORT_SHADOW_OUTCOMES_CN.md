# Shadow Outcome 回填报告

当前文件作为占位模板存在。实际报告请运行：

```bash
set -a
. ./.env.postgres
. ./.env.redis
. ./.env.dashboard
. ./.env.chain
set +a
go run -tags shadow ./cmd/lpbot --config=configs/config.shadow.toml --shadow-outcomes-backfill --report-shadow-outcomes
```

默认输出仍会覆盖本文件。

## 目标字段

- `decision_trace_id`
- `pool_id`
- `horizon`
- `score_total`
- `selected`
- `simulated_fee_usd`
- `simulated_gas_usd`
- `simulated_il_usd`
- `simulated_net_pnl_usd`
- `max_drawdown_usd`
- `label`
- `invalid_rate`
- `selected_sample_count`
- `gas_adjusted_positive_rate`
- `high_score_vs_low_score`

## 当前口径

- `simulated_net_pnl_usd` 以 shadow position mark 为基础，再减去估算 gas。
- `lvr` 仍未接入。
- 没有足够 mark 的样本会标为 `invalid`，不会强行补算。
- `PASS` 必须满足：
  - `realized_sample_count >= 20`
  - `invalid_rate <= 30%`
  - `avg_net_pnl > 0`
  - `median_net_pnl > 0`
  - `p10_net_pnl` 不低于阈值
  - `high_score_vs_low_score = better`
- 样本不足时最多 `WARN`，不会直接 `PASS`
