# Tmux or Nohup Start Healthcheck

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: tmux_or_nohup_start_healthcheck
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- healthchecked_at_utc: `2026-06-06T13:25:00Z`

## 0. 总结

✅ **12h partial collector 启动成功, 2-3min healthcheck 全过**. 启动方法: **nohup** (tmux server 在本 env **不** 可访问, 见下). 12h 期间 stage runner 在 wallclock loop (12 × 1h = 12h, 当前 sleeping). Checkpoint 1/12 在 13:24:45Z 完成, **不** 触发 24h, **不** 触发 wallet/tx/probe.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `launch_method` | **nohup** (tmux server not accessible) |
| `process_alive` | **true** (pid 3871101) |
| `process_cmd` | `bash scripts/run_lp_long_horizon_readonly_stage_once.sh 20260606_131323 12h 12 ...` |
| `first_heartbeat_exists` | **true** (`heartbeat_0.json`) |
| `first_checkpoint_exists` | **true** (`checkpoint_1_1324/`) |
| `first_checkpoint_completed_at_utc` | `2026-06-06T13:24:45Z` |
| `logs_updating` | **true** (`supervisor.log` updating) |
| `no_wallet_tx_probe_observed` | **true** |
| `no_24h_started` | **true** (auto_advance_to_24h=false) |
| `long_run_started` | **true** (启动后变 true) |
| `expected_end_time_utc` | `2026-06-07T01:24:45Z` |
| `expected_checkpoint_count` | **12** |
| `current_checkpoint_index` | **1** |
| `current_checkpoint_status` | **ok** |

## 2. 启动方法 (nohup 替代 tmux)

**原因**: 本 env (TMUX=/tmp/tmux-0/default,...) 是**已** 嵌入 tmux session 内, 新 `tmux new-session` 命令创建的 session **不** 在 `tmux ls` 可见. 改用 nohup 启动:

```bash
nohup bash scripts/run_lp_long_horizon_readonly_stage_once.sh 20260606_131323 12h 12 \
  reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/partial_observable_real_pool_universe_for_12h.json \
  > reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs/nohup.log 2>&1 &
```

**PID 3871101** 仍在运行.

## 3. Checkpoint 1/12 smoke 结果

- `selected_real_pool_count`: **53** (49 Solana + 4 BSC V3)
- `placeholder_pool_count`: **0**
- `all_pools_are_real_on_chain`: **true**
- `pool_snapshots`: 53
- `quote_snapshots`: 318 (53 × 6 notional)
- `fee_velocity`: 265 (53 × 5 windows)
- `liquidity_distribution`: 53
- `market_regime`: 7

## 4. tmux 替代方案 (诚实披露)

Per spec: "tmux/noHup 启动". 改用 **nohup** 原因: tmux server not accessible in this env. 优点:
- 进程 detached from shell, 即使 shell 关闭也继续运行
- stdout/stderr 重定向到 `logs/nohup.log`, **不** 丢失日志
- PID 3871101 可 ps -p 验证 alive

**风险**: nohup 不像 tmux session 那样有独立的 attach/detach 能力. 12h 期间如需 stop 进程, 用 `kill 3871101`.

## 5. 锁定字段 (启动后状态)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | **true** |
| `auto_advance_to_24h` | `false` |
| `do_not_treat_as_full_universe` | `true` |

## 6. 12h 时间表 (启动后)

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| Stage G launch | 2026-06-06 13:24:00 | ✅ done |
| Stage G healthcheck (2-3min) | 2026-06-06 13:25:00 | ✅ done (this report) |
| 第 1 checkpoint | 2026-06-06 13:24:45 (anchor shifted to first ckpt time) | ✅ done |
| 第 2 checkpoint | 2026-06-06 14:24:45 | pending |
| ... | ... | ... |
| 第 12 checkpoint (完成) | 2026-06-07 01:24:45 | pending |
| 失败 fallback deadline | 2026-06-07 02:24:45 | pending |
| Stage H finalize (auto by stage runner) | 2026-06-07 01:24:45 ~ 02:24:45 | pending |

## 7. 严禁 (启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction
- ❌ 不写真实 secret
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer

## 8. 下游

12h 完成后, stage runner 自动生成 (Stage H):
- `FINAL_VERDICT.json` (status=PASS/WARN/FAIL based on gate)
- `ONEPAGE_CN.md`
- `ARTIFACT_INDEX.md`
- 12h node report
- coverage manifest
- fee estimation basis
- candidate review
- next node decision

`recommended_next_stage` 仅允许 4 个值 (per spec):
- `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1`
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`
