# R1 12h Full Wallclock — Supervisor Fix Options (CN)

- **stage**: `LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1`
- **current_supervisor_status**: structural off-by-one in `scripts/run_lp_long_horizon_r1_12h_stage_once.sh`
- **purpose**: 文档化 3 个候选 fix 方案, 供 user 在 reopen R1 时选择. **本 stage 不实施任何 fix.**

## 0. 背景

R1 12h v3 (RUN_ID `20260607_191500`) supervisor 启动时声明:
```
[r1_12h start] RUN_ID=20260607_191500 DURATION_HOURS=12 CHECKPOINT_COUNT=12 START_TS=1780859772 END_TS=1780902972 SLEEP_SECONDS=3600
```

- START_TS = `2026-06-07T19:16:12Z`
- END_TS = `2026-06-08T07:16:12Z` (= START + 12h)
- DURATION_HOURS=12
- CHECKPOINT_COUNT=12
- SLEEP_SECONDS=3600

但 supervisor 实际循环是 start-anchored (第一次 collect 在 t=0):
```
loop 1: t=0,    collect_1, sleep 3600   # collect_1 ends at t=62s
loop 2: t=3600, collect_2, sleep 3600   # ends at t=3619s
...
loop 12: t=11*3600, collect_12, exit    # ends at t=11h 5m 17s
```

**总 wallclock = 1 + sum(overheads) + 11 * 3600 = 1 + 314 + 39600 = 39915s ≈ 实测 39917s**

永远 = `(N-1) * SLEEP + sum(overheads)`, 不到 `N * SLEEP`. N=12, S=3600 时永远 ≈ 11h. 这是**结构性 off-by-one**, 不是 v3 run 的问题.

要真正达到 12h wallclock, 必须改 supervisor. 3 个候选 fix:

## 1. Fix A: 13 iterations (N+1)

### 1.1 思路

跑 13 次 collect. 第 13 次 collect 在 t≈12h 时执行, 之后立即退出 (不 sleep).

### 1.2 改哪里

`scripts/run_lp_long_horizon_r1_12h_stage_once.sh`:

```bash
# 旧:
CHECKPOINT_COUNT=12
for i in $(seq 1 12); do
    collect_and_write_ckpt_$i
    if [ $i -lt 12 ]; then
        sleep 3600
    fi
done

# 新 (Fix A):
CHECKPOINT_COUNT=13
for i in $(seq 1 13); do
    collect_and_write_ckpt_$i
    if [ $i -lt 13 ]; then
        sleep 3600
    fi
done
```

或者不改 N, 但在 sleep 3600 之后, **额外**让 loop 多跑一次空 collect 触发 FINALIZE 时刻到 t=12h (不推荐, 与 v3 设计冲突).

### 1.3 优缺点

| 优点 | 缺点 |
|---|---|
| 改动最小, 1 行 `12 → 13` | ckpt 命名变化 (checkpoint_13_xxxx); 12h 数据有 13 个 ckpts 而非 12; 与 "12h full wallclock" 名字更不一致 |
| 兼容现有 collect+write 代码 | 12h "full" 仍是 misleading; 真实 wallclock ≈ 12h 5m (13 个 ckpt + drift) |
| 测试容易 | 13 ckpt 数据的下游消费者 (READING script, report) 可能需要适配 |
| supervisor log 容易 debug | 名字 "12h full wallclock" 仍 misleading, 应改名 "12h+ wallclock" |

### 1.4 适用场景

如果 user 接受 "13 个 ckpt = ~12h 真实 wallclock", 这是最小改动方案.

## 2. Fix B: sleep-first-collect

### 2.1 思路

第一次 collect 推迟到 t=S (= 3600s). supervisor 启动后立即 sleep 3600s, 然后第一次 collect. 之后正常 11 次 sleep+collect. 总共 12 个 ckpt, 总 wallclock ≈ 12h.

### 2.2 改哪里

`scripts/run_lp_long_horizon_r1_12h_stage_once.sh`:

```bash
# 旧:
for i in $(seq 1 12); do
    collect_and_write_ckpt_$i
    if [ $i -lt 12 ]; then
        sleep 3600
    fi
done

# 新 (Fix B):
sleep 3600  # 第一次 collect 推迟到 t=1h
for i in $(seq 1 12); do
    collect_and_write_ckpt_$i
    if [ $i -lt 12 ]; then
        sleep 3600
    fi
done
```

### 2.3 优缺点

| 优点 | 缺点 |
|---|---|
| 保留 12 个 ckpt 命名, 与原 design 一致 | 启动后 1h "空窗" 没有 collect, 看起来 idle |
| 真实 wallclock ≈ 12h (匹配命名) | 如果 wrapper / supervisor 启动失败, 1h 后才 detect, debug 慢 |
| 12 ckpt 数据均匀覆盖 1h~12h | 与 v0/v1/v2/v3 的 "t=0 first collect" 模式不同, 旧 artifacts 不直接 comparable |
| 改动 1 行 (前置 sleep) | v0/v1/v2/v3 data 的 mtime 序列 (0, 1h, 2h, ..., 11h) 改变为 (1h, 2h, ..., 12h) |
| | 旧 12h data dir (`20260606_131323`) 不能直接对比, 需重新校准 |

### 2.4 适用场景

如果 user 重视 "12 ckpts 均匀覆盖 12h" 的命名一致性, 这是优选. 但要放弃与 v0/v1/v2/v3 data 的 mtime 直接 comparable.

## 3. Fix C: start_ts_anchored scheduler mode

### 3.1 思路

使用 `start_ts_anchored_interval_3600` 模式 (在 WALLCLOCK_PROOF 中作为 `allowed_scheduler_modes` 存在, 但 v3 未使用). 此模式从 start_ts 开始, 每 S 秒触发一次 collect, 直到 N 次后退出. 每次 collect 完成后 sleep 至下一个 (start_ts + i*S) 时刻.

### 3.2 改哪里

可能需要:
- `scripts/run_lp_long_horizon_r1_12h_stage_once.sh` 加 scheduler_mode 选择
- 改 supervisor 的 sleep 目标 (从 "until 3600s elapsed" 改为 "until start_ts + i*3600")
- `data/lp_long_horizon_r1_12h_full_wallclock/.../logs/aggregate_summary.json` 中的 scheduler_mode 字段

### 3.3 优缺点

| 优点 | 缺点 |
|---|---|
| 时序最稳定, 每次 collect 严格锚定到 start_ts + i*S | 改动最大, 涉及多个文件 |
| drift 仅来自 collect overhead, sleep 自动补偿 | 需要 unit test 覆盖 scheduler mode 选择 |
| 真实 wallclock 严格 ≈ 12h (与 N*S + 漂移补偿) | 旧 code path `completion_anchored_sleep_3600` 与 `start_ts_anchored_interval_3600` 并存, 需要 dual-mode test |
| 命名 "12h full wallclock" 在此 mode 下是真的 | 需要新 test coverage: `TestSchedulerMode_StartTsAnchored_Reaches12h` |

### 3.4 适用场景

如果 user 重视 "12h 严格 wallclock", 这是最严谨方案. 但需要 code change 较大 + 新 tests.

## 4. 三方案对比总表

| 维度 | Fix A (13 iters) | Fix B (sleep-first) | Fix C (start_ts anchored) |
|---|---|---|---|
| Code 改动 | 1 行 | 1 行 (前置 sleep) | 多文件 + 新 tests |
| ckpt 数量 | 13 (命名变化) | 12 (不变) | 12 (不变) |
| 真实 wallclock | ≈ 12h 5m | ≈ 12h (前端空 1h) | 严格 ≈ 12h |
| 与 v0/v1/v2/v3 data 可比性 | 不直接 (ckpt 数不同) | 不直接 (mtime 序列不同) | 不直接 (scheduler mode 不同) |
| 名字 "12h full wallclock" 一致性 | 略 misleading | 一致 | 一致 |
| Test 改动 | 极少 | 极少 | 较多 |
| 风险 | 低 | 中 (启动 debug 慢) | 中-高 (multi-mode) |
| 推荐度 | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

## 5. 不推荐的方案 (不实施)

- **不重跑 v3 as-is**: 必然得到同样的 PARTIAL (supervisor 拓扑不变)
- **不延长 sleep 时间 (e.g. 3600s → 3700s)**: 仍 start-anchored 拓扑, 永远 (N-1)*S, 不是 fix
- **不调小 N (e.g. 12 → 10)**: 那叫 "10h full wallclock", 不是 12h
- **不用 12h data + 1h padding**: 数据本身只 11h, padding 30m 不是真实 data
- **不取消 ckpt_count 必须 12 的硬约束**: 任何"为了跑 12h 而改 ckpt 命名"的 fix 都是自欺

## 6. 决策权

Fix 方案的选择权在 **user**, 不在 assistant. assistant 只能:
- 实施 user **显式** 选定的 fix (with `Fix A/B/C` 标识)
- 在 reopen 时, 提示 user 选 fix
- 在 code review 时, 验证 fix 落地

**严禁** assistant 自行决定 fix path. **严禁** 在 PAUSE record 中隐式选 fix.

## 7. 一句话

3 个候选 fix 各自有 trade-off. user 必须显式选. 任何 "as-is 再跑一次" 都会再次 PARTIAL. 选 fix → 改 code → 新 stage → duration ≥ 43200 → artifacts 自洽 → 才算 R1 12h thread PASS. 选 fix + 改 code 不在本 PAUSE record 范围.
