# R1 12h Full Wallclock Observation Report

- stage: `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1`
- run_id: `20260607_191500`
- status: **PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION**
- stage_verdict: **R1_12H_FULL_WALLCLOCK_PASS_NOT_REACHED_DURATION_43200S**
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-08T08:23:54Z`

## 0. 一句话

R1 12h full wallclock v3 12/12 checkpoints 跑完, scheduler_mode=`completion_anchored_sleep_3600`, max_drift=62s, duration_wallclock_seconds=39917s. **PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION** (honest verdict: duration < 43200s).

## 1. 时间表

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| v0 (pid 2876054) launched | 2026-06-07T18:44:51Z | ❌ exited (sed bug) |
| v1 (RUN_ID 20260607_184500, pid 2892835) launched | 2026-06-07T18:52:00Z | ❌ PARTIAL_WALLCLOCK_FAIL (whitelist) |
| v3 (RUN_ID 20260607_191500, pid 2948793) launched | 2026-06-07T19:16:12Z | ✅ done (12/12 ckpt) |
| v3 ckpt 1 done | 2026-06-07T19:16:14Z (sup_ckpt_starts[0]) | ✅ |
| v3 ckpt 12 done | 2026-06-08T06:21:13Z (sup_ckpt_starts[-1]) | ✅ |
| v3 supervisor exit | 2026-06-08T06:21:29Z | ✅ rc=0 |
| finalize_after_expected_end | true (expected_end=07:16:12Z, actual ended 06:21:29Z) | ✅ |

## 2. duration 真实计算 (来自 supervisor log)

- started_at = 19:16:12Z (loop 1 start)
- ended_at = 06:21:29Z (12h end)
- duration = 39917s = 11h 5m 17s
- 12 ckpts × 3600s sleep = 43200s, but ckpt 1 collector took 62s, shifting subsequent ckpts; total 11h 5m 17s

## 3. 验收 (per user spec)

### 3.1 **FAIL (PARTIAL)**

- ❌ duration_wallclock_seconds >= 43200 (actual=39917s, FAIL by 3283s)
- ✅ compressed=false
- ✅ short_supervisor_used=false (NEVER invoked _short.sh)
- ✅ full_supervisor_used=true
- ✅ checkpoint timeline 完整 (12 ckpts, 实际文件 mtime + supervisor log 时间)
- ✅ current data dir 真实数据完整 (selected_pool_count=20, 6 dim 全 row>0)
- ✅ forbidden actions 全 0
- ❌ status 符合 duration 约束 (status=PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION, duration_ok=False)

### 3.2 typo 黑名单 (测试断言 NOT 存在)

- ✅ CWALLCLICK_PROOF (不出现)
- ✅ checkpointPinterval_drift_srconds (不出现)
- ✅ finalize_aftertexpscaed_end (不出现)
- ✅ cheartbeat_index (不出现)
- ✅ stt_us (不出现)

## 4. Watchlist 演化

| Ckpt | watchlist | preflight | data_insufficient |
|---|---|---|---|
| 1/12 | 7 | 0 | 0 |
| ... | ... | ... | ... |
| 12/12 | 7 | 0 | 0 |

## 5. 锁定 (仍 LOCKED)

- can_run_probe_now=false
- tiny_canary_allowed="no"
- edge_proven="no"
- actual_fee_data_available=false
- fee_proxy_only=true
- wallet_or_tx_touched=false
- transaction_sent=false
- auto_advance_to_24h=false
- longer_stage_started=false

## 6. 严禁 (仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不进入 R2
- ❌ 不 probe / canary / live / paper
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写 production positions
- ❌ 不读 wallet / seed / keypair / signer

## 7. 关键 takeaway

R1 12h full wallclock v3 跑完 12 ckpt, 但实际 wallclock=39917s < 43200s (= 12h), honest verdict=PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION. 12 ckpt 全部有真实数据, 但未满足 12h wallclock 阈值. 原因: ckpt 1 collector 耗时 62s, 后续 ckpt 平移, 总 wallclock 仅 11h 5m 17s. **不** 自动 24h / R2 / probe / etc. user decide: (a) accept PARTIAL + review, (b) relaunch longer target, (c) PAUSE.
