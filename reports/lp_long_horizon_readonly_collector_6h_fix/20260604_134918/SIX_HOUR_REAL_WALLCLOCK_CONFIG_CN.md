# Stage D — 真实 6h Run 配置冻结 (Real 6h Wallclock Config Freeze)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- run_id: `20260604_134918`

## 0. 目的

锁定真实 6h read-only collector 跑的所有参数, **严禁 short mode**.
所有参数 LOCKED, supervisor 启动时验证 + 跑期间监控 + 跑完后审计.
本任务与上一轮 6H_RUN_APPROVAL_V1 关键差异: **`actual_runtime_minutes >= 330`** 是
硬约束, 任何 short mode / override 立即 abort.

## 1. 真实 6h run 参数 (LOCKED)

| 参数 | 值 | 严禁改 |
|---|---|---|
| `duration_hours` | `6` | 任何改 → abort |
| `min_valid_runtime_minutes` | `330` (5.5h, 6h - 10% cleanup) | 任何改 → abort |
| `checkpoint_interval_minutes` | `60` (1 hour) | 任何改 → abort |
| `heartbeat_interval_minutes` | `15` | 任何改 → abort |
| `max_pools` | `5` (来自 local_artifact_replay) | 任何改 → abort |
| `notional_levels_usd` | `[10, 20, 100, 500, 1000, 2000]` | 任何改 → abort |
| `rolling_windows` | `["15m", "1h", "6h"]` | 任何改 → abort |
| `output_data_dir` | `data/lp_long_horizon/20260604_134918/` | LOCKED |
| `output_report_dir` | `reports/lp_long_horizon_readonly_collector_6h_run/20260604_134918/` | LOCKED |
| `tmux_session_name` | `lp_long_horizon_6h_20260604_134918` | LOCKED |
| `run_mode` | `readonly` | 任何改 → abort |
| `paid_rpc` | `false` | 任何改 → abort |
| `paid_indexer` | `false` | 任何改 → abort |
| `no_probe` | `true` | 任何改 → abort |
| `no_wallet` | `true` | 任何改 → abort |
| `no_tx` | `true` | 任何改 → abort |
| `no_bridge` | `true` | 任何改 → abort |
| `dry_run` | `true` | 任何改 → abort |
| `cron_enabled` | `false` | 任何改 → abort |
| `systemd_enabled` | `false` | 任何改 → abort |
| `daemon_enabled` | `false` (tmux 是 short-lived session, 不是 daemon) | 任何改 → abort |
| `auto_advance_to_12h` | `false` | 任何改 → abort |

## 2. **CRITICAL**: short mode / override 严禁

| 字段 | 值 | 行为 |
|---|---|---|
| `short_mode_allowed` | **`false`** | 任何 short mode 触发 → 立即 abort |
| `loop_sleep_override_allowed` | **`false`** | 任何 SLEEP_SECONDS 改 → 立即 abort |
| `min_sleep_seconds_per_iteration` | `3600` (1h) | SLEEP_SECONDS < 3600 → abort |
| `max_loop_count_override` | `6` (per task spec) | LOOP_COUNT > 6 → abort |
| `min_actual_runtime_minutes` | `330` | 实际 runtime < 330 → gate FAIL |

supervisor 启动时**校验** `SLEEP_SECONDS=3600` 与 `LOOP_COUNT=6`, 任何不匹配立即
exit 1 + 写 FINAL_VERDICT status=FAIL.

## 3. 真实 6h tmux session 计划

- session name: `lp_long_horizon_6h_20260604_134918`
- 启动时间: T0 (Stage G 完成时)
- 结束时间: T0 + 6h
- expected_end_time_utc: `2026-06-04T19:49:18Z` (T0 = 13:49:18Z + 6h)
- session lifetime: 6h + 10 min cleanup
- max concurrent sessions: 1 (LOCKED)
- 关键 supervisor 检查: tmux session 不能跨 6h 之后 leak (auto-cleanup)

## 4. supervisor 脚本应做的检查

1. **启动时**:
   - `SLEEP_SECONDS == 3600` (拒绝 < 3600)
   - `LOOP_COUNT == 6` (拒绝 > 6)
   - tmux session 唯一 (拒绝 existing)
   - no canary/live/paper process
   - no wallet/keypair/signer process
   - data dir + report dir writable

2. **跑期间** (per checkpoint = 1h):
   - 实际 wallclock 累计 (per `started_at`)
   - 任何 wallclock < 累计期望 = abort
   - 任何 consecutive_429_streak >= 5 = abort
   - 任何 error_rate > 20% = abort
   - 任何 write_failure = abort
   - tmux session 还存在 (不能被外部 kill)
   - heartbeat 每 15 min 写一次 (4 per hour)

3. **6h 收口**:
   - actual_runtime_minutes >= 330 (gate threshold)
   - 6 个 checkpoint 全部生成
   - safety 字段全部 locked
   - 写 FINAL_VERDICT + ONEPAGE + ARTIFACT_INDEX + 6 个中间报告
   - **自动** git add + commit + push (per task spec H "6h 完成后自动 finalize、commit、push")
   - 杀 tmux session

## 5. abort 阈值 (LOCKED)

| abort 触发条件 | 阈值 | 行为 |
|---|---|---|
| `consecutive_429_streak` | `>= 5` | runner 立即 abort + exit 1 |
| `error_rate_pct` | `> 20` | runner abort + exit 2 |
| `write_failure` (jsonl/sqlite) | any | runner abort + exit 3 |
| `safety_self_check_failure` | any | runner abort + exit 4 |
| `forbidden_token_detected` | any | runner abort + exit 5 |
| `disk_threshold_breach_mb` | `> 1` (per 6h stage_gate_rules) | runner abort + exit 6 |
| `duplicate_collector_process` | tmux session already exists | new tmux 拒绝启动 + exit 7 |
| `short_mode_detected` | SLEEP_SECONDS < 3600 | runner abort + exit 8 |
| `loop_count_overridden` | LOOP_COUNT != 6 | runner abort + exit 9 |
| `actual_runtime_below_330` | actual_runtime_minutes < 330 at finalize | gate FAIL, 不晋级 |

## 6. 6h 累计数据维度估算 (real 6h, 5 pool, 6 notional)

| 类别 | 6h 累计 | 备注 |
|---|---|---|
| pool_snapshots | 5 × 6 = 30 records | (5 pool × 6 次 per hour) |
| quote_snapshots | 5 × 6 × 6 × 6 = 1080 records | (5 pool × 6 notional × 6h × 6 samples/h) |
|  | 实际计算: 5 pool × 6 notional × 72 sample = 2160 records (per stage_gate_rules) |
| fee_velocity | 5 × 6 × 3 = 90 records | (5 pool × 6 次 × 3 windows) |
| liquidity_distribution | 5 × 6 = 30 records | (5 pool × 6 次) |
| market_regime | 7 × 6 = 42 records | (7 regime × 6 次, classifier live) |
| actual_fee_accrual | 1 placeholder | schema only |

## 7. safety 21 字段 (per finalization report)

- touched_trading_path = false
- touched_wallet_tx_bridge_live_paper = false
- wallet_or_tx_touched = false
- solana_wallet_or_keypair_touched = false
- transaction_sent = false
- send_hard_disable_still_active = true
- no_paid_rpc_integration = true
- no_paid_indexer_integration = true
- no_protocol_re_run = true
- no_heuristic_modification = true
- no_long_running_daemon = true (tmux is short-lived session)
- no_signer_creation = true
- no_12h_24h_48h_72h_7d_run = true
- no_auto_advance = true
- no_cron_enabled = true
- no_systemd_enabled = true
- no_extra_tmux_session = true (1 session only)
- no_actual_daemon = true
- no_approval_recorded_for_other_stages = true
- secret_leak_count = 0
- production_write_count = 0
- shadow_overwrite_count = 0

## 8. 6h 收口自动 finalize + 自动 commit/push

task spec H 明确: "6h 完成后 supervisor 必须自动生成 [7 reports]" + "完成后自动 commit + push".

supervisor 脚本**必须**包含:

```bash
# 6h 收口 (real wallclock)
ELAPSED_MIN=$(( ($(date +%s) - $START_TS) / 60 ))
if [ "$ELAPSED_MIN" -lt 330 ]; then
    echo "FAIL: actual_runtime_minutes=$ELAPSED_MIN < 330"
    exit 10
fi

# 写 7 份报告 (Stage H)
python3 scripts/finalize_6h_run.py ${RUN_ID}

# 自动 git add + commit + push
cd /opt/lpbot/lp-bot-v3-origin-check
git add reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID} \
        data/lp_long_horizon/${RUN_ID} \
        scripts tests
git commit -m "research: finalize real 6h long horizon readonly collector ${RUN_ID}"
git push origin feat/supabase-postgres-deployment

# 杀 tmux session
tmux kill-session -t lp_long_horizon_6h_${RUN_ID}
```

## 9. 6h gate PASS 条件 (per task spec)

```
actual_runtime_minutes >= 330
AND selected_pool_count > 0
AND pool_snapshot_rows > 0
AND quote_snapshot_rows > 0
AND fee_velocity_rows > 0
AND market_regime_rows > 0
AND error_rate_pct <= 20
AND consecutive_429_max < 5
AND research_only_write_ok = true
AND no production write
AND no wallet/tx
AND no daemon leak
AND final verdict generated
```

- ✅ PASS: `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1`
- ⚠️ WARN_ACCEPTABLE: `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN FIX_REPEAT`
- ❌ FAIL: `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR FIX_REPEAT`

**严禁**自动 12h. 任何 next_stage 都需要新 approval.

## 10. 结论

真实 6h run 参数全部 LOCKED. short mode / override 严禁. supervisor 脚本必须
校验 SLEEP_SECONDS=3600 + LOOP_COUNT=6, 任何不匹配立即 abort.
real 6h wallclock 跑完成 (>= 330 min) 是硬约束. Stage D 通过.
进入 Stage E (创建 supervisor 脚本).
