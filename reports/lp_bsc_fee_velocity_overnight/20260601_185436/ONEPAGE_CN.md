# BSC Fee Velocity Overnight Artifact Sync Onepage

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_ARTIFACT_SYNC_AND_ROOT_CAUSE_V1`
- run_id: `20260601_185436`
- sync_status: `partial`
- final_synced: `yes`
- final_is_current: `no`
- current_run_status: `running`
- selected_pool_count_checkpoint: `8`
- selected_pool_count_final: `0`
- swap_log_count_final: `0`
- fee_ready_pool_count_final: `0`
- root_cause: `unknown`
- rerun_now: `no`
- rerun_requires_smoke_first: `yes`
- tiny_canary_allowed: `no`

## 结论

当前可以确认的不是“任务已经结束”，而是：

- VPS 产物里已有数据、日志和 checkpoint
- final 目录存在一个旧的 FAIL 收口
- 当前 tmux 仍在跑，说明这个 final 不是当前活跃 run 的权威结果

下一步优先做的是输入路径和 smoke 修复，而不是直接重跑 full overnight。
