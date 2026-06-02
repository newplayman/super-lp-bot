# Overnight Run 当前运行状态（RUNNING）

- run_id: `20260601_185436`
- decision_reason: `auto_runner_active`
- tmux_session_active: `True`
- runner_process_active: `True`
- runner_pid: `2982617`
- runner_user: `deploy`

## 进度

- selected_pool_count: `8`
- pool_count: `8`
- completed / expected: `34 / 40`
- progress_pct: `85.0%`
- pool_fee_velocity rows: `0`
- swap_logs_decoded rows: `0`

## final 状态

- final_exists: `True`
- final_is_current: `False`
- final_is_stale_or_unverified: `True`
- authoritative_status_source: `checkpoint_and_run_log`
- final_overwritten_this_run: `False`

## 下一步

```text
recommended_next_stage = WAIT_FOR_OVERNIGHT_COMPLETION
```

runner 仍在跑；不覆盖 final/FINAL_VERDICT.json；不发交易；不允许 probe / canary / live / paper。
