# Shadow Outcome 回填报告

当前文件作为占位模板存在。实际报告请运行：

```bash
go run ./cmd/lpbot --config=configs/config.live.toml --shadow-outcomes-backfill --report-shadow-outcomes
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

## 当前口径

- `simulated_net_pnl_usd` 以 shadow position mark 为基础，再减去估算 gas。
- `lvr` 仍未接入。
- 没有足够 mark 的样本会标为 `invalid`，不会强行补算。
