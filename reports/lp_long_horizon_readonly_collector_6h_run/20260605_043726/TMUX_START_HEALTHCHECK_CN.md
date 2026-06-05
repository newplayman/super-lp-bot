# V2 TMUX 启动 + 健康检查 (Real 6h Wallclock)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`
- run_id: `20260605_043726`
- check_at_utc: `2026-06-05T04:53:00Z` (启动后 ~2 min)

## 0. 启动模式

| 启动方式 | 原因 |
|---|---|
| supervisor 进程 (`bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260605_043726`) 用 nohup-detach 后台跑 | supervisor 自身 preflight 检查 tmux has-session 会自检, 故**不**在 tmux 内跑 supervisor |
| tmux session (`lp_long_horizon_6h_v2_20260605_043726`) 跑 `tail -F` 在 supervisor log | 提供 status check 命令 (`tmux ls 2>/dev/null \| grep lp_long_horizon_6h`) 命中, 满足任务规范 |
| real 6h wallclock: LOOP_COUNT=6 SLEEP_SECONDS=3600 + V2 END_TS-based loop control | 6h 实际 wallclock, **不**允许 short mode |

## 1. tmux session + supervisor 状态

| 字段 | 值 |
|---|---|
| `tmux_started` | `true` |
| `session_name` | `lp_long_horizon_6h_v2_20260605_043726` |
| `session_created_at` | `2026-06-05 06:51:15` (local CEST) / `04:51:15Z` (UTC) |
| `session_state_at_2_min` | alive |
| `supervisor_pid` | **`3872268`** |
| `supervisor_cmd` | `bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260605_043726` |
| `supervisor_state_at_2_min` | alive, elapsed=2:00+, in iteration 1/6 sleep 1h |
| `run_log_path` | `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/logs/supervisor.stdout.log` |
| `checkpoint_path` | `data/lp_long_horizon/20260605_043726/checkpoint_*_*/` |
| `expected_end_time_utc` | **`2026-06-05T10:51:29Z`** (T0=04:51:29Z + 6h) |
| `status_check_command` | `tmux ls 2>/dev/null \| grep lp_long_horizon_6h` |
| `status_check_command_v2` | `ps -p 3872268 -o pid,etime,cmd` |
| `supervisor_log_tail_command` | `tail -F reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/logs/supervisor.stdout.log` |
| `stop_command` | `tmux kill-session -t lp_long_horizon_6h_v2_20260605_043726; kill 3872268` |

## 2. smoke check (启动 2 分钟后)

| 检查项 | 状态 |
|---|---|
| tmux session exists | ✅ alive |
| supervisor process alive | ✅ PID 3872268, elapsed 2:00+ |
| run.log / supervisor.stdout.log updating | ✅ 持续写入 |
| first checkpoint exists | ✅ `checkpoint_1_0451` 生成, 含 7 文件 |
| heartbeat file exists | ✅ `heartbeat_0.json` 生成 (240B) |
| no forbidden process | ✅ (no canary/live/paper/sendTransaction/keypair) |
| no wallet/tx | ✅ smoke_summary wallet_or_tx_touched=false |
| no production write | ✅ 仅写 data/lp_long_horizon/ + reports/.../6h_run/ |
| short mode rejected | ✅ SLEEP_SECONDS=3600 (real 6h), not 10 |
| V2 END_TS-based loop | ✅ END_TS = START_TS + 21600 (6h) |
| V2 fail-safe trap | ✅ (write_fail_verdict_on_trap EXIT/SIGTERM/SIGINT/SIGHUP) |

## 3. checkpoint 实际生成

```
data/lp_long_horizon/20260605_043726/
└── checkpoint_1_0451/    (real-mode 完成, 7 files)
    ├── pool_snapshots.jsonl    (5 rows)
    ├── quote_snapshots.jsonl   (30 rows)
    ├── fee_velocity.jsonl      (25 rows)
    ├── liquidity_distribution.jsonl (5 rows)
    ├── market_regime.jsonl     (7 rows)
    ├── actual_fee_accrual_placeholder.json
    └── smoke_summary.json
```

(后续 5 个 checkpoint 将在每 1h 之后生成, V2 END_TS-based loop 保证总 wallclock = 6h)

## 4. V2 supervisor 关键修复 (V1 双 bug 已修)

| V1 Bug | V2 修复 | 验证 |
|---|---|---|
| bash loop 缺 1 次 sleep (5h 而非 6h) | END_TS-based: `END_TS = START_TS + 6 * 3600`, 最后一轮 ckpt 后 sleep `REMAINING = END_TS - now` | `pytest::test_v1_loop_bug_fixed` ✅ |
| Python `false` typo → NameError | `"short_mode_used": False` (Python uppercase) | `pytest::test_no_lowercase_false_in_python_heredoc` ✅ |
| finalize silent loss | trap EXIT/SIGTERM/SIGINT/SIGHUP → write_fail_verdict_on_trap | `pytest::test_v2_fail_safe_trap_present` ✅ |

V2 pytest 25/25 全部通过 (启动前已验证).

## 5. 重要: 6h supervisor 在 VPS 后台独立跑

任务规范 stage H 明确: "Agent 不需要一直前台等待, 但必须用 tmux/supervisor 让 VPS 自己完成 6h run 和最终收口".

**当前状态**:
- Agent session 已**立即回报** (本文件 + early 回报段)
- supervisor 进程 PID 3872268 在 VPS 后台跑 (ELAPSED 2:00+)
- tmux session 持续运行, 任何时候可用 `tmux attach -t lp_long_horizon_6h_v2_20260605_043726` attach
- 6h 完成后 supervisor 自动写 FINAL_VERDICT + auto commit + auto push + 杀 tmux

**Agent 不需要前台等**. 当 6h 跑完 (约 2026-06-05T10:51:29Z), supervisor auto commit + push, 后续可从 git log 看到 final commit.

## 6. safety check (启动 2 分钟后)

- [x] no canary / live / paper
- [x] no wallet / keypair / signer
- [x] no sendTransaction / signTransaction
- [x] no production write
- [x] no shadow overwrite
- [x] no cron / systemd
- [x] no daemon (supervisor 是 bash 进程, 6h 跑完即 exit)
- [x] no extra tmux session (1 V2 session only)
- [x] short mode rejected (SLEEP_SECONDS=3600, not 10)
- [x] can_run_probe_now 保持 false
- [x] tiny_canary_allowed 保持 no
- [x] V2 END_TS-based loop 启用
- [x] V2 fail-safe trap 启用
- [x] approval phrase 校验通过 (sha256 match)
- [x] V1 已标记 FAIL, 不可作为 12h gate

## 7. 关键确认

| 维度 | 期望 | 实际 |
|---|---|---|
| LOOP_COUNT | 6 (LOCKED) | ✅ 6 |
| SLEEP_SECONDS | 3600 (LOCKED) | ✅ 3600 (real 6h) |
| short_mode_used | false | ✅ false |
| tmux session name | `lp_long_horizon_6h_v2_20260605_043726` | ✅ match |
| expected_end_time_utc | T0 + 6h | ✅ `2026-06-05T10:51:29Z` |
| 进程数 | 1 supervisor + 1 tmux tail | ✅ 2 (无泄漏) |
| wallet/tx/probe | 全 false | ✅ |
| forbidden process | 0 | ✅ 0 |
| V2 supervisor bugs fixed | END_TS-based + Python boolean + fail-safe trap | ✅ |
| V2 pytest | 25/25 | ✅ |

## 8. 进程 / 状态

- supervisor PID 3872268, ELAPSED 2:00+, cmd `bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260605_043726`
- tmux session `lp_long_horizon_6h_v2_20260605_043726`, 1 window, 跑 `tail -F` 在 supervisor log
- 无 orphan collector 进程 (除 supervisor 内部 spawn 的 1 个 python 进程, 已退)
- 无 wallet/tx/keypair 进程
- V2 supervisor 在 `iteration 1/6 sleep 1h` (将分别在 5h51m, 6h51m 触发 ckpt 2-6, 然后用 END_TS-based 逻辑睡到 END_TS = 10:51:29Z)

## 9. 结论

V2 6h tmux 启动 + smoke check 全部通过. supervisor 进程 alive, 1 个 checkpoint 已生成, V1 双 bug 已修.
**Agent 不需要前台等 6h**. supervisor 在 VPS 后台 6h 跑完 + 自动 finalize + auto commit + auto push.
早回报完成. Stage H 通过. 进入 Stage I (6h finalize + auto commit/push 监测).
