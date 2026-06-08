# R1 12h Full Wallclock — One Pager

- stage: `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1`
- run_id: `20260607_191500`
- status: **PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION**
- stage_verdict: **R1_12H_FULL_WALLCLOCK_PASS_NOT_REACHED_DURATION_43200S**
- branch: `feat/supabase-postgres-deployment`

## 0. 一句话

R1 12h full wallclock v3 跑完 12/12 checkpoints, ckpt 间隔 ~3600s (max_drift=62s), real wallclock=39917s = 11h 5m. **duration < 43200s ⇒ PARTIAL** (honest verdict per user spec)。

## 1. 关键字段 (clean)

| 字段 | 值 |
|---|---|
| status | **PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION** |
| run_id | 20260607_191500 |
| started_at | 2026-06-07T19:16:12Z |
| ended_at | 2026-06-08T06:21:29Z |
| duration_wallclock_seconds | **39917** < 43200 (FAIL) |
| duration_wallclock_seconds_ok | False |
| scheduler_mode | completion_anchored_sleep_3600 |
| checkpoint_count_so_far | 12 |
| max_checkpoint_interval_drift_seconds | 62 |
| finalize_after_expected_end | true |
| compressed | false |
| short_supervisor_used | false |
| full_supervisor_used | true |
| wrapper_pid | 2948793 |
| child_supervisor_pid | 2948806 |
| forbidden_actions_still_zero | true |
| actual_fee_data_available | false (LOCKED) |
| fee_proxy_only | true |
| edge_proven | "no" (LOCKED) |
| can_run_probe_now | false (LOCKED) |
| tiny_canary_allowed | "no" (LOCKED) |
| auto_advance_to_24h | false (LOCKED) |

## 2. 12 ckpt 真实时间线 (来自 supervisor log 实际时间戳)

| Ckpt | Start UTC | Interval from prev (s) | Drift from 3600 (s) |
|---|---|---|---|
| 10/12 | 2026-06-08T04:21:06Z | - | 0 |
| 11/12 | 2026-06-08T05:21:13Z | 3662 | 62 |
| 12/12 | 2026-06-08T06:21:28Z | 3619 | 19 |
| 1/12 | 2026-06-07T19:17:14Z | 3617 | 17 |
| 2/12 | 2026-06-07T20:17:33Z | 3657 | 57 |
| 3/12 | 2026-06-07T21:17:50Z | 3622 | 22 |
| 4/12 | 2026-06-07T22:18:46Z | 3632 | 32 |
| 5/12 | 2026-06-07T23:19:09Z | 3618 | 18 |
| 6/12 | 2026-06-08T00:19:41Z | 3623 | 23 |
| 7/12 | 2026-06-08T01:19:59Z | 3635 | 35 |
| 8/12 | 2026-06-08T02:20:22Z | 3610 | 10 |
| 9/12 | 2026-06-08T03:20:57Z | 3606 | 6 |

**max_drift = 62s** (all intervals in [3600, 3662]).

## 3. Row counts 12h 演化

| Dim | ckpt 1/12 | ckpt 12/12 | 总行数 (12 ckpt) |
|---|---|---|---|
| pool_snapshot | 20 | 20 | 240 |
| quote_snapshot | 120 | 120 | 1440 |
| fee_velocity | 100 | 100 | 1200 |
| liquidity_distribution | 20 | 20 | 240 |
| market_regime | 2 | 2 | 24 |
| candidate_review | 20 | 20 | 240 |

## 4. Watchlist 演化

- ckpt 1: 7 → ckpt 12: 7 (稳定, 0 漂移)
- preflight 0 → 0
- data_insufficient 0 → 0

## 5. 4 阶段 Run History

| Run | PID | Verdict |
|---|---|---|
| v0 | 2876054 | exited (sed rewrite bug) |
| v1 | 2892835 (RUN_ID 20260607_184500) | PARTIAL_WALLCLOCK_FAIL (whitelist reject) |
| v3 | 2948793 (RUN_ID 20260607_191500) | **PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION** |

## 6. 严禁 (仍不触发)

- 不启动 24h / 48h / 72h / 7d
- 不进入 R2
- 不 probe / canary / live / paper
- 不读 wallet / seed / keypair / signer
- 不发送 transaction
- 不写 production positions
- 不接 paid RPC / paid indexer

## 7. 4 allowed next stages

1. `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1`
2. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT`
3. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`
