# LPBOT 研究状态

当前状态：`LP strategy research frozen`

- final freeze report path: `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000/FINAL_VERDICT.json`
- edge_proven = `no`
- tiny_canary_allowed = `no`
- current_full_strategy = `FAIL`
- fixed_horizon = `STOP`
- intent_lifecycle = `STOP`
- Tier B = `PAUSE`
- Tier C = `BATCH_REJECTED`
- risk-aware short-hold = `STOP`
- pool-regime-aware = `STOP`
- fee-velocity / exit-depth = `STOP`
- next recommended action = `STOP_LP_RESEARCH_NOW`

警示：

- 当前不得运行 live / canary / paper。
- 当前不得把任何研究结论转成 micro-live。
- 当前只允许阅读历史报告、补文档、做工程清理。
- `docs/runbooks/base-canary-ops.md`、`docs/runbooks/vps-shadow-deployment.md`、`scripts/canary_cycle.sh` 等历史入口仅作归档保留，不代表当前允许执行。

未来 reopen conditions：

- 需要更可信的 fee accrual / exit depth / trader-holder concentration 数据。
- 需要更高频、可证明 entry-safe 的 pool snapshot pipeline。
- 需要新的策略假设，不能继续沿用当前 fixed-horizon / simple short-hold / fee-depth 小修路线。
- 需要清晰的 go/no-go gate：`sample_count >= 300`、`p10/p5/p1` 不危险、`opportunity retention` 可接受、`fee_minus_exit_cost` 不明显为负、无 lookahead。

如果未来重启，先读：

- `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000/LPBOT_FINAL_ONEPAGE_CN.md`
- `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000/REOPEN_CONDITIONS_CN.md`
- `/Users/bendu/lp-bot/v3/reports/final_freeze/20260531_124000/NEXT_PROJECT_OPTIONS_CN.md`

## LP Scale Economics Addendum

- scale economics 重开题已完成，且已走完整条只读验证链。
- `20 / 100 / 500 / 1000 / 2000U` virtual notional 已测试。
- quote/depth、fee velocity、fixed cost、IL/LVR 已分别拆解审计。
- `fixed_cost = 0` 仍无 positive proxy。
- `IL/LVR = 0` 仍无 positive proxy。
- 当前结论仍为 `STOP_LP_RESEARCH_NOW`。
- 当前不允许 probe / canary / live。
