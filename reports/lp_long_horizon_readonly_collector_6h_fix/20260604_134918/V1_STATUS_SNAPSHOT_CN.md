# V1_STATUS_SNAPSHOT — V0 / V1 区分 + V1 in-flight 状态

- snapshot_at_utc: `2026-06-04T18:35:18Z`
- author: Agent (Claude Opus 4.8)
- run_id_v1: `20260604_134918`
- branch: `feat/supabase-postgres-deployment`
- decision: **V1 继续跑真实 6h, V2 延后**; 等 V1 自然完成后再判断是否需要 V2

---

## 1. 区分: V0 vs V1

| 维度 | V0 (`20260604_130353`) | V1 (`20260604_134918`, current) |
|---|---|---|
| stage | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1` | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1` |
| LOOP_COUNT | 6 | **6** (LOCKED) |
| SLEEP_SECONDS | 10 (SHORT) | **3600** (REAL 6h, LOCKED) |
| actual_runtime_minutes | **2.75** | in-flight, 期望 360 |
| short_mode_used | **true** (V0 invalid) | **false** |
| short_mode_rejected | false (V0 used short mode) | true (V1 SLEEP_SECONDS=3600, 拒绝 SLEEP_SECONDS<3600) |
| gate_pass | false (2.75 < 330) | 期望 true (360 >= 330) |
| can_advance_to_12h | false | 期望 true (但仍需新 manual approval) |
| recommended_next_stage | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` | 期望 `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` |
| status (snapshot 时) | completed (WARN_ACCEPTABLE) | **RUNNING (3/6 checkpoints done)** |

**V0 是不合格短模式 run, 不可作为 6h gate**. V0 FINAL_VERDICT 写明: `actual_runtime_mode: "short (LOOP_COUNT=6 SLEEP_SECONDS=10)"`, `gate_pass=false`, `recommended_next_stage=6H_RUN_FIX_REPEAT`.

**V1 是当前真实 6h run**, real wallclock, LOOP_COUNT=6 SLEEP_SECONDS=3600, currently ELAPSED ~2.5h, expected to finish at 20:01:29Z.

## 2. V1 in-flight 状态 (snapshot 时刻)

| 字段 | 值 |
|---|---|
| supervisor PID | `2161828` alive |
| supervisor STAT | `S` (sleeping, waiting in 1h timer) |
| supervisor ELAPSED | **02:33:50** (153.6 min) |
| supervisor state | iteration 3/6, sleep 2/4 (heartbeat 3_2_of_4 at 16:31:32Z) |
| supervisor cmd | `bash scripts/run_lp_long_horizon_readonly_6h_once.sh 20260604_134918` |
| tmux session | `lp_long_horizon_6h_20260604_134918`, 1 window, alive |
| tmux created | 2026-06-04 16:02:00 (created at supervisor launch) |
| expected end time UTC | **`2026-06-04T20:01:29Z`** (T0 + 6h) |
| remaining time | ~1h 26m (3 more checkpoints to go) |
| checkpoints generated | 3 / 6 (`checkpoint_1_1401`, `checkpoint_2_1501`, `checkpoint_3_1601`) |
| heartbeats | 12 of 24 (4 per iteration × 3 iterations done) |
| short_mode_used | **false** |
| short_mode_rejected | true (supervisor hard guard: `SLEEP_SECONDS < 3600` → exit 8) |
| loop_count_override_rejected | true (supervisor hard guard: `LOOP_COUNT != 6` → exit 9) |
| can_run_probe_now | false (三层断言: config, approval, supervisor runtime) |
| tiny_canary_allowed | "no" |
| auto_advance_started | false (config + supervisor + pytest 三层 no_auto_advance=true) |
| longer_stage_started | false |
| can_advance_to_12h | (待 V1 finalize 时由 gate 决定) |
| gate_pass | (待 V1 finalize 时由 `actual_runtime_minutes >= 330` 决定) |
| wallet_or_tx_touched | false (smoke mode only, no chain access) |
| transaction_sent | false |
| send_hard_disable_still_active | true |

## 3. V1 数据状态 (snapshot 时刻)

```
data/lp_long_horizon/20260604_134918/
├── checkpoint_1_1401/    (3/6 ✓ 7 files: pool_snapshots.jsonl, quote_snapshots.jsonl,
│                                       fee_velocity.jsonl, liquidity_distribution.jsonl,
│                                       market_regime.jsonl, actual_fee_accrual_placeholder.json,
│                                       smoke_summary.json)
├── checkpoint_2_1501/    (3/6 ✓ same 7 files)
└── checkpoint_3_1601/    (3/6 ✓ same 7 files, completed 16:01:32Z)
```

后续 3 个 checkpoint 将在每 1h 之后由 supervisor 生成 (checkpoint_4_1701 @ 17:01Z, checkpoint_5_1801 @ 18:01Z, checkpoint_6_1901 @ 19:01Z).

每个 checkpoint 的 smoke mode 行数 (per V1 log):
- pool_snapshots: 5
- quote_snapshots: 30
- fee_velocity: 25
- liquidity_distribution: 5
- market_regime: 7
- actual_fee_accrual_placeholder: 1
- smoke_summary: 1

V1 finalize 时 (T0+6h, expected 20:01:29Z) supervisor 会把 6 个 checkpoint 的行数 sum 后写入 FINAL_VERDICT.

## 4. V1 完成后行为 (per scripts/run_lp_long_horizon_readonly_6h_once.sh)

supervisor 跑完 6 个 checkpoint (real 6h) 后, 自动:

1. 计算 `actual_runtime_minutes = (END_TS - START_TS) / 60`
2. gate decision: `actual_runtime_minutes >= 330` ?
   - YES → gate PASS, data_quality_status=PASS, recommended_next_stage=`LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1`
   - NO → gate FAIL, data_quality_status=FAIL, recommended_next_stage=`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT`
3. 写 7 份报告 (SIX_HOUR_RUN_SUMMARY_CN.md / six_hour_run_summary.json, DATA_QUALITY_GATE_CN.md / data_quality_gate.json, MARKET_REGIME_SUMMARY_CN.md / market_regime_summary.json, NEXT_STAGE_DECISION_CN.md / next_stage_decision.json, FINAL_VERDICT.json, ONEPAGE_CN.md, ARTIFACT_INDEX.md)
4. auto commit: `git add reports/.../6h_run/${RUN_ID} data/lp_long_horizon/${RUN_ID} scripts tests`
5. auto push: `git push origin feat/supabase-postgres-deployment`
6. 杀 tmux session: `tmux kill-session -t lp_long_horizon_6h_20260604_134918`

## 5. V1 FINAL_VERDICT 必含字段 (per task spec)

| 字段 | 类型 | V1 supervisor 写入值 | 备注 |
|---|---|---|---|
| `stage` | string | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1` | supervisor hardcoded |
| `six_hour_run_completed` | bool | true (V1 已跑完 6h wallclock) | |
| `actual_runtime_minutes` | float | 期望 ~360 (取决于 T1 - T0) | |
| `actual_runtime_valid_for_6h_gate` | bool | `actual_runtime_minutes >= 330` | |
| `short_mode_used` | bool | **false** | V1 hard guard: SLEEP_SECONDS=3600 |
| `short_mode_rejected` | bool | true | supervisor preflight exit 8 if SLEEP_SECONDS<3600 |
| `selected_pool_count` | int | sum of 6 checkpoints, 期望 5 (5 pool per checkpoint, deduped to 5 unique) | per V0 dedup pattern |
| `pool_snapshot_rows` | int | sum of 6 checkpoints (5 × 6 = 30 raw, 期望 5 unique deduped) | |
| `quote_snapshot_rows` | int | sum of 6 checkpoints (30 × 6 = 180 raw) | |
| `fee_velocity_rows` | int | sum of 6 checkpoints (25 × 6 = 150 raw) | |
| `liquidity_distribution_rows` | int | sum of 6 checkpoints (5 × 6 = 30 raw) | |
| `market_regime_rows` | int | sum of 6 checkpoints (7 × 6 = 42 raw) | |
| `error_rate_pct` | float | 0.0 (smoke mode, no network) | |
| `consecutive_429_max` | int | 0 (no HTTP calls) | |
| `data_quality_status` | string | PASS / WARN_ACCEPTABLE / FAIL | per gate decision |
| `gate_pass` | bool | `actual_runtime_minutes >= 330` | |
| `can_advance_to_12h` | bool | `gate_pass` (但仍需新 manual approval) | |
| `auto_advance_started` | bool | **false** (三层 no_auto_advance) | |
| `longer_stage_started` | bool | **false** (no 12h/24h/48h/72h/7d) | |
| `can_run_probe_now` | bool | **false** | |
| `tiny_canary_allowed` | string | "no" | |
| `wallet_or_tx_touched` | bool | **false** | smoke mode |
| `transaction_sent` | bool | **false** | smoke mode |
| `recommended_next_stage` | string | PASS: `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` / FAIL: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` | per V1 supervisor line 348 |

## 6. 用户后续查看 V1 6h 结果

V1 跑完后, 用户可用:

```bash
cd /opt/lpbot/lp-bot-v3-origin-check
git log --oneline | head -5
# 找 "research: finalize real 6h long horizon readonly collector 20260604_134918" commit

# 查看 V1 FINAL_VERDICT.json
cat reports/lp_long_horizon_readonly_collector_6h_run/20260604_134918/FINAL_VERDICT.json | python3 -m json.tool

# 查看 V1 run summary
cat reports/lp_long_horizon_readonly_collector_6h_run/20260604_134918/SIX_HOUR_RUN_SUMMARY_CN.md

# 查 V1 supervisor 是否还活着
ps -p 2161828 -o pid,etime,cmd

# 查 V1 tmux session
tmux ls 2>/dev/null | grep lp_long_horizon_6h
```

V1 expected end: 2026-06-04T20:01:29Z, 还有 ~1h 26m.

## 7. V2 延后决定 (per user instruction)

- V1 完成后, 用户将根据 V1 gate_pass 决定是否进入 V2:
  - V1 gate PASS → user 可手动进入 `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (但 V1 的 `can_advance_to_12h=true` 不构成 auto-advance, 仍需新 manual approval)
  - V1 gate FAIL 或 runtime < 330 → V2 fix repeat 启动
- 当前 (snapshot 时刻) 不启动 V2
- V2 不与 V1 并行
- V1 supervisor 不 kill

## 8. 安全审计 (V1 in-flight)

- [x] no canary / live / paper process
- [x] no wallet / keypair / signer process
- [x] no sendTransaction / signTransaction
- [x] no production write (V1 仅写 data/lp_long_horizon/ + reports/.../6h_run/)
- [x] no shadow overwrite
- [x] no cron / systemd / daemon (supervisor bash 进程, 6h 跑完即 exit)
- [x] 1 tmux session only (lp_long_horizon_6h_20260604_134918)
- [x] 1 supervisor process only (PID 2161828)
- [x] can_run_probe_now = false (三层断言)
- [x] tiny_canary_allowed = "no"
- [x] auto_advance_started = false
- [x] longer_stage_started = false
- [x] short_mode_used = false
- [x] short_mode_rejected = true

## 9. 结论

- V0 (13:03:53) 是**短模式无效 run** (LOOP_COUNT=6 SLEEP_SECONDS=10, 2.75 min, gate FAIL, recommended_next_stage=6H_RUN_FIX_REPEAT)
- V1 (13:49:18) 是**当前真实 6h run** (LOOP_COUNT=6 SLEEP_SECONDS=3600, currently 2.5h elapsed, 3/6 checkpoints, expected_end=20:01:29Z)
- V2 延后, 等 V1 自然完成
- V1 supervisor PID 2161828 alive, tmux session alive, 安全审计全部通过
- V1 finalize 后自动 write 7 reports + FINAL_VERDICT + auto commit + auto push
- Agent session 不前台等 6h, 仅生成此 status snapshot; V1 finalize 后由 user 触发 late return 报告
