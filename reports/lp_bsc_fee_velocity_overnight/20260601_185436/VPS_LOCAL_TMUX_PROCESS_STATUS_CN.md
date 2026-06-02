# VPS 本机 tmux / process 状态

- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- phase: C
- run_id: `20260601_185436`
- environment: `vps_local`
- status_source: `local_vps_process_check`

## 结果

| 字段 | 值 |
|---|---|
| tmux_session_active | **yes** |
| tmux_session_name | `lp_bsc_fee_velocity_overnight_20260601_185436` |
| tmux_session_owner_user | `deploy` |
| runner_process_active | **yes** |
| runner_pid | `2982619` |
| runner_user | `deploy` |
| runner_started_local | `2026-06-01 21:13:13` |
| runner_elapsed_seconds_approx | `36828`（≈10h13m） |
| runner_max_hours | `10` |
| runner_cpu_pct_sampled | `7.7%` |
| runner_stat | `R` |

## 命令（已脱敏）

```text
python3 scripts/lp_bsc_fee_velocity_overnight_runner.py \
  --run-id 20260601_185436 \
  --output-dir /tmp/lp_bsc_fee_velocity_overnight_20260601_185436 \
  --max-hours 10 \
  --checkpoint-minutes 60 \
  --windows 24h,72h,7d,14d,30d
```

## 解释

1. 当前 shell 用户 `root` 默认 `tmux ls` 只能看到 root 自己的 daemon (`/tmp/tmux-0`)。runner 的 tmux session 属于 `deploy` (uid 1000，daemon socket `/tmp/tmux-1000/default`)，因此必须用 `sudo -u deploy tmux ls` 才能看到。
2. `ps` 不受 tmux daemon 隔离，能直接确认 PID 2982619 仍在 Run 状态、占用约 7.7% CPU。
3. runner 启动时设置 `--max-hours 10`，从 19:13:16Z 起，按 wall-clock 已超过 10 小时，预计在本日内自然退出。但**当前 process 仍 active**。

## 对 final 权威的影响

```text
runner_process_active = yes
→ final/FINAL_VERDICT.json MUST NOT be overwritten
→ authoritative_status_source = checkpoint_and_run_log
→ finalize 只能写 RUNNING_STATUS，禁止生成新 FINAL_VERDICT_REBUILT
```
