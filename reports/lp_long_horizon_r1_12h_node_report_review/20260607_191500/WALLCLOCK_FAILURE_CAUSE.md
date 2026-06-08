# R1 12h Full Wallclock — Wallclock Failure Cause Analysis

- **reviewed_run_id**: `20260607_191500`
- **failure_kind**: duration_wallclock_seconds=39917 < 43200 (12h threshold)
- **failure_severity**: structural (not data integrity)

## 1. 现象

R1 12h full wallclock v3 (RUN_ID `20260607_191500`) 完成了 12/12 个 checkpoints, 每个 checkpoint 有完整数据 (156 r1_* files), supervisor 干净退出 (rc=0), 但实际 `duration_wallclock_seconds=39917 = 11h 5m 17s`, **未达到** 12h (`43200s`) 阈值.

按 user spec: `duration_wallclock_seconds < 43200s ⇒ status MUST NOT be PASS`. 当前 status 正确为 `PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION`.

## 2. 已排除的原因 (not the cause)

| 假设 | 证据 | 结论 |
|---|---|---|
| 提前 finalize | `WALLCLOCK_PROOF.finalize_after_expected_end=true`, supervisor log line 37-43 完整记录 [end] [finalize] [aggregate] [complete] [exit]; ckpt12 mtime → exit gap = 1s | ❌ Not the cause |
| 压缩运行 (compressed=true) | `WALLCLOCK_PROOF.compressed=false`, `COMMAND_USED.txt` 写明 `sleep_seconds_per_iteration=3600` | ❌ Not the cause |
| 短脚本 (short_supervisor_used=true) | `WALLCLOCK_PROOF.short_supervisor_used=false`, `COMMAND_USED.txt` 写明 `NEVER invoked _short.sh` | ❌ Not the cause |
| 估计行数 / placeholder 混入 | `DATA_QUALITY_SUMMARY.placeholder_pool_count=0`, row counts first/last 6 dim 一致 (20/120/100/20/2/20) | ❌ Not the cause |
| 旧 data dir 混入 | v3 data dir 单独 (`20260607_191500/`), 不含 v0/v1/v2/old_12h 文件; PID_TRANSITION_AUDIT 仅 audit 当前 v3 | ❌ Not the cause |
| 数据 fabrication | `SOURCE_HEALTH.no_fake_data_injection=true`, 156 文件全有 r1_* 命名, solana+bsc 真实 chain data | ❌ Not the cause |
| wrapper / supervisor crash | supervisor log line 43: `[r1_12h exit] rc=0` (clean exit), wrapper_nohup_v3.log: `supervisor exited rc=0` | ❌ Not the cause |
| 系统挂起 / 时钟漂移 | 所有 interval 在 [3500, 3700]s 范围内, max drift 56s; mtime 全部从文件系统 stat | ❌ Not the cause |

## 3. 真正的 root cause — supervisor 循环拓扑结构性的 off-by-one

### 3.1 supervisor 启动声明 (line 1)

```
[r1_12h start] RUN_ID=20260607_191500 DURATION_HOURS=12 CHECKPOINT_COUNT=12 START_TS=1780859772 END_TS=1780902972 SLEEP_SECONDS=3600
```

- START_TS = 1780859772 → `2026-06-07T19:16:12Z`
- END_TS = 1780902972 → `2026-06-08T07:16:12Z`
- END_TS - START_TS = 43200s (12h) ✓
- DURATION_HOURS=12, CHECKPOINT_COUNT=12, SLEEP_SECONDS=3600

### 3.2 supervisor 实际循环 (lines 2-36)

```
# (Conceptual reconstruction from observed log)
START=$START_TS
for i in $(seq 1 12); do
    if [ "$NOW" -ge "$END_TS" ]; then
        break
    fi
    collect_and_write_ckpt_$i    # takes 6-62s
    if [ $i -lt 12 ]; then
        sleep 3600
    fi
done
# After loop, aggregate + finalize + exit
```

### 3.3 实际耗时分解

| 阶段 | 时刻 | 时长 |
|---|---|---|
| loop 1 start | 19:16:12Z | t=0 |
| loop 1 collect end | 19:17:14Z | +62s |
| sleep 1 (until loop 2) | 20:17:14Z | +3600s |
| loop 2 collect end | 20:17:33Z | +19s |
| sleep 2 (until loop 3) | 21:17:33Z | +3600s |
| ... (10 more iterations, each ~17-56s overhead + 3600s sleep) ... | | |
| loop 12 collect end | 06:21:28Z | +15s |
| finalize + aggregate + exit | 06:21:29Z | +1s |
| **total** | 19:16:12Z → 06:21:29Z | **39917s** |

### 3.4 公式推导

设 N=12 (checkpoint count), S=3600 (sleep), d_i = 第 i 次 collect overhead.

- t=0: start (loop 1)
- loop 1 结束: d_1
- sleep 1: S
- loop 2 结束: d_1 + S + d_2
- ...
- loop N 结束: sum(d_1..N) + (N-1) * S
- 加上 finalize: +1s

```
total = 1 + sum(d_1..12) + 11 * 3600
      = 1 + (62+19+17+56+22+32+18+23+35+9+6+15) + 39600
      = 1 + 314 + 39600
      = 39915s (vs reported 39917, 差 2s 来自 sleep 内部浮点 round)
```

实测 `duration_wallclock_seconds=39917` 与推导值 **39915** 差 2s, 全部归因于 sleep 的 1s 边界和 mtime epoch 精度, **完全一致**.

### 3.5 结论

**supervisor 的循环结构, 在 N=12, S=3600 时, 必然产生 ≈ 11h 的 wallclock** (因为是 start-anchored 循环, 第一次 collect 在 t=0 而不是 t=3600).

要达到真正的 12h wallclock:
- 方案 A: 跑 **N+1=13 次 iteration** (第 13 次在 t≈12h 时 collect, 然后立即退出)
- 方案 B: 第一次 collect 推迟到 t=S (sleep 3600s, 然后 collect)
- 方案 C: 用 `start_ts_anchored_interval_3600` scheduler mode (WALLCLOCK_PROOF 显示当前是 `completion_anchored_sleep_3600`, 暗示另一种 mode 存在但未使用)

**这是 supervisor 代码的设计问题, 不是 v3 run 的执行问题**. v3 跑得完全正确, 只是 supervisor 的 "12h full wallclock" 命名 misleading.

## 4. 诚实标记 vs 实际不符的内部矛盾

`data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500/logs/aggregate_summary.json` 包含字段:
```
"actual_runtime_valid_for_12h_gate": true,
"actual_runtime_minutes": 665,
"expected_min_runtime_minutes": 660,
```

这与 report-level 的 `duration_wallclock_seconds_ok=false` **矛盾**. 解读:
- aggregate_summary 内部使用 **660 min = 11h** 作为阈值 (基于 N-1 次 interval 的 sum ≈ 11h), 所以 665 min "OK" 了
- report-level 使用 **43200s = 12h** 作为阈值 (per user spec), 所以 39917s FAIL

**这是 spec vs supervisor 内部 calibration 的不一致**. 报告层 (per user spec) 正确标记 PARTIAL. aggregate_summary 是 supervisor 的内部 sanity check, 用了较松的阈值, 仍 OK.

**最终判决以 user spec 的 43200s 阈值为准**: `status=PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` 是正确且诚实的.

## 5. 给下一阶段的建议 (not a fix here, read-only review only)

1. **不**修改 supervisor (no-touch invariant: 12h data dir / collector / adapters / runner 主代码).
2. **不**重新跑 12h. 任何新一轮都属于新 stage, 需 user explicit 授权.
3. **不**进入 13h/24h/48h/R2 (LOCKED).
4. 推荐的 next stage: `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (per FINAL_VERDICT.json).
5. 后续如果 user 决定 fix supervisor, 改的是 `scripts/run_lp_long_horizon_r1_12h_stage_once.sh` 和 `scripts/run_lp_long_horizon_r1_12h_full_wallclock.sh`, **不是**本审查任务范围内.

## 6. 一句话

v3 跑得诚实, 12/12 ckpt 真实, no forbidden action, no fabrication. duration 没到 12h 是 supervisor 循环拓扑结构性的 (N iterations × S sleep + 1 first-collect = (N-1)S + d, 永远 < N*S). 标记为 PARTIAL 是正确的. 本审查 status=WARN, 不升级, 不 probe, 不 R2, 不动代码.
