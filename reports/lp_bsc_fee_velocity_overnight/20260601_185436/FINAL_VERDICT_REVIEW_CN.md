# FINAL_VERDICT 审阅

- status: `FAIL`
- stage: `LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_BACKFILL_V1`
- run_id: `20260601_185436`
- selected_pool_count: `0`
- windows_completed: `["14d","24h","30d","72h","7d"]`
- swap_log_pool_count: `0`
- swap_log_count: `0`
- fee_ready_pool_count: `0`
- volume_usd_total: `0`
- pool_fee_usd_proxy_total: `0`
- recommended_next_stage: `LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_REPEAT`
- wallet_or_tx_touched: `false`
- tiny_canary_allowed: `no`

## 结论

这个 `FINAL_VERDICT.json` 是一个旧收口文件，不是当前正在跑的 tmux 任务的实时结果。

依据：

- `checkpoint/state.json` 显示 `selected_pool_count = 8`
- `logs/run.log` 在 `2026-06-02T04:37:40Z` 之后仍有新 checkpoint
- `tmux` 会话仍存在
- `final/FINAL_VERDICT.json` 的修改时间早于当前 checkpoint 和日志

因此，这个 final 只能作为历史失败态留档，不能作为当前运行的权威结论。
