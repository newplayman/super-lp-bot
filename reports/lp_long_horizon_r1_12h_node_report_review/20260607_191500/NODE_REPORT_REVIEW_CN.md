# R1 12h Full Wallclock Node Report Review — RUN_ID 20260607_191500

- **stage**: `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1`
- **reviewed_run_id**: `20260607_191500`
- **source_stage**: `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V1`
- **source_status**: `PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` (honest)
- **review_verdict**: **WARN** (artifacts honest, run did not reach 12h)
- **branch**: `feat/supabase-postgres-deployment`
- **review_audited_at_utc**: `2026-06-08T18:30:00Z`
- **reviewer**: node_report_reviewer_subagent (read-only, no code changes)

## 0. 一句话

R1 12h full wallclock v3 (RUN_ID `20260607_191500`) 的 12/12 checkpoints 全部有真实数据, supervisor 干净退出 (rc=0), forbidden actions 全 0, 没有压缩运行 / 短脚本 / 旧数据混入 / 提前 finalize. **duration_wallclock_seconds=39917 < 43200s** 的失败原因是 **supervisor 循环拓扑结构性的**, 而非数据造假. artifacts **honest** 标记了 `status=PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` 和 `duration_wallclock_seconds_ok=false`. 本审查 `status=WARN`, **不升级到 PASS**, **不声称 edge_proven**, **不进入 R2/probe/canary/live**.

## 1. 关键数字 (来自原 artifacts)

| 字段 | 值 | 来源 |
|---|---|---|
| status | `PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` | `FINAL_VERDICT.json` |
| run_id | `20260607_191500` | `FINAL_VERDICT.json` |
| started_at | `2026-06-07T19:16:12Z` | `WALLCLOCK_PROOF.json` + supervisor log line 1 |
| ended_at | `2026-06-08T06:21:29Z` | `WALLCLOCK_PROOF.json` + supervisor log line 43 |
| duration_wallclock_seconds | **39917** (< 43200, **FAIL**) | `WALLCLOCK_PROOF.json` |
| duration_wallclock_seconds_ok | **false** ✅ (honest) | `WALLCLOCK_PROOF.json` |
| scheduler_mode | `completion_anchored_sleep_3600` | `WALLCLOCK_PROOF.json` |
| checkpoint_count | 12/12 ✅ | `WALLCLOCK_PROOF.json` |
| max_checkpoint_interval_drift_seconds | 62 (≤ 200, OK) | `WALLCLOCK_PROOF.json` |
| compressed | **false** ✅ | `WALLCLOCK_PROOF.json` |
| short_supervisor_used | **false** ✅ | `WALLCLOCK_PROOF.json` |
| full_supervisor_used | **true** ✅ | `WALLCLOCK_PROOF.json` |
| wrapper_pid | 2948793 | `WALLCLOCK_PROOF.json` + `COMMAND_USED.txt` |
| child_supervisor_pid | 2948806 | `WALLCLOCK_PROOF.json` |
| finalize_after_expected_end | true | `WALLCLOCK_PROOF.json` |
| forbidden_actions_still_zero | **true** ✅ | `FORBIDDEN_ACTIONS_AUDIT.json` |
| actual_fee_data_available | false (LOCKED) | `FINAL_VERDICT.json` |
| fee_proxy_only | true (LOCKED) | `FINAL_VERDICT.json` |
| edge_proven | "no" (LOCKED) | `FINAL_VERDICT.json` |
| can_run_probe_now | false (LOCKED) | `FINAL_VERDICT.json` |
| tiny_canary_allowed | "no" (LOCKED) | `FINAL_VERDICT.json` |

## 2. 12 checkpoint 真实时间线 (来自文件 mtime + supervisor log 交叉验证)

按 ckpt_index 升序:

| Ckpt | Start UTC (mtime) | Interval (s) | Drift from 3600 (s) | supervisor log 一致? |
|---|---|---|---|---|
| 1/12 | 2026-06-07T19:17:14Z | — | 62 (startup) | ✅ "loop 1 ok in 62s" |
| 2/12 | 2026-06-07T20:17:33Z | 3619 | 19 | ✅ |
| 3/12 | 2026-06-07T21:17:50Z | 3617 | 17 | ✅ |
| 4/12 | 2026-06-07T22:18:46Z | 3656 | 56 | ✅ |
| 5/12 | 2026-06-07T23:19:09Z | 3623 | 23 | ✅ |
| 6/12 | 2026-06-08T00:19:41Z | 3632 | 32 | ✅ |
| 7/12 | 2026-06-08T01:19:59Z | 3618 | 18 | ✅ |
| 8/12 | 2026-06-08T02:20:22Z | 3623 | 23 | ✅ |
| 9/12 | 2026-06-08T03:20:57Z | 3635 | 35 | ✅ |
| 10/12 | 2026-06-08T04:21:06Z | 3609 | 9 | ✅ |
| 11/12 | 2026-06-08T05:21:13Z | 3607 | 7 | ✅ |
| 12/12 | 2026-06-08T06:21:28Z | 3615 | 15 | ✅ |

- **max_drift = 62s** (ckpt 1 启动开销; 后续 11 个 interval 漂移范围 [6, 56]s, **均 ≤ 60s**)
- ckpt 1 → ckpt 12 实际 wallclock = **39874s** = 11h 4m 34s
- supervisor 启动 → ckpt 1 mtime gap = **62s** (与 loop 1 "ok in 62s" 一致)
- ckpt 12 mtime → supervisor exit gap = **1s** (干净退出, 无 lag)
- supervisor **expected_end = 2026-06-08T07:16:12Z** (12h), actual ended 06:21:29Z, 提前 54m 43s 退出

## 3. Root cause: duration < 43200s 的诚实解释

**不是** 提前 finalize. **不是** 短脚本. **不是** 压缩运行. **不是** 旧数据混入. **不是** 估计行数.

**Root cause 是 supervisor 循环拓扑结构性的 off-by-one**:

supervisor 启动时 (line 1):
```
[r1_12h start] RUN_ID=20260607_191500 DURATION_HOURS=12 CHECKPOINT_COUNT=12 START_TS=1780859772 END_TS=1780902972 SLEEP_SECONDS=3600
```

`END_TS - START_TS = 43200s = 12h`, 但 supervisor 的循环是:

```
for i in 1..12:                  # 12 iterations
    start_iter_i
    collect + write ckpt_i      # overhead 6-62s per ckpt
    sleep 3600s                  # except for last
```

也就是说:
- 第 1 次迭代在 t=0 开始
- 第 1 次迭代结束 + sleep = ckpt 2 在 t≈3600s
- ...
- 第 12 次迭代结束在 t≈11×3600 + 漂移 ≈ 11h 5m

**这个循环结构在 N=12, sleep=3600s 时, 总 wallclock 必然 ≈ 11h (而不是 12h)**. 要达到 12h, supervisor 必须跑 **13 个 iterations** (最后一次 sleep 后立刻退出), 或者把第一次 collect 推迟到 t=3600s.

这不是数据问题, 不是 fabrication, 不是 banned action. 这是 supervisor 的设计决定了 "12h full wallclock" 这个名字在拓扑上就是 misleading 的. 实际跑的 wallclock **永远** 是 (N-1) * sleep + drift.

**`PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` 标记正确**. 真实数据完整, honest verdict.

## 4. 数据完整性 audit

| 项 | 期望 | 实际 | OK? |
|---|---|---|---|
| data dir ckpts | 12 dirs | 12 dirs (checkpoint_1_1916 ... checkpoint_12_0621) | ✅ |
| r1_* data files total | 12 ckpt × 13 files = 156 | 156 | ✅ |
| 6 dim row counts (per ckpt) | pool=20, quote=120, fee=100, liq=20, regime=2, candidate=20 | 同上 (一致) | ✅ |
| placeholder_pool_count | 0 | 0 | ✅ |
| watchlist_count_first | 7 | 7 | ✅ |
| watchlist_count_last | 7 | 7 | ✅ |
| watchlist_count_drift | 0 | 0 | ✅ |
| chains_skipped | ["base"] | ["base"] | ✅ |
| no_fake_data_injection | true | true | ✅ |
| sources_overall solana | reachable | reachable | ✅ |
| sources_overall bsc | reachable | reachable | ✅ |
| sources_overall base | unreachable | unreachable | ✅ |
| coingecko | reachable | reachable | ✅ |
| dexscreener | unreachable | unreachable | ✅ |
| meteora_dlmm_api | unreachable | unreachable | ✅ |

**数据诚实, 无 placeholder, 无 estimated baseline, 无 prior baseline mix.**

## 5. 旧 data dir / v0 / v1 / v2 隔离检查

| 目录 | 状态 | v3 是否引用? |
|---|---|---|
| `data/lp_long_horizon_r1_12h_full_wallclock/20260607_184500/` (v1 partial) | 存在, 8 files | ❌ 没引用, separate dir |
| `data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500/` (v3 current) | authoritative | ✅ this is v3 |
| `data/lp_long_horizon_12h/20260606_131323/` (old 12h smoke) | 隔离 (no-touch invariant) | ❌ 未触碰 |
| `data/lp_long_horizon_r1_12h_compressed/20260607_171000/` (v2 R1 short) | 隔离 (no-touch invariant) | ❌ 未触碰 |
| `data/lp_long_horizon_r1_12h_smoke/20260607_163000/` (smoke) | 隔离 (no-touch invariant) | ❌ 未触碰 |

`WALLCLOCK_PROOF.run_history_audit` 字段是 reference 字符串, 不读 v0/v1 data dir. `PID_TRANSITION_AUDIT.json` 也只 audit 当前 v3 pid. **No old data mixed.**

## 6. Forbidden actions recheck

| Action | Status |
|---|---|
| 启动 24h | ❌ 没启动 |
| 启动 48h / 72h / 7d | ❌ 没启动 |
| 进入 R2 | ❌ 没进入 (LOCKED) |
| probe / canary / live / paper | ❌ 没运行 |
| 读 wallet / keypair / seed / signer | ❌ 没读 |
| 发送 transaction (mint / add / remove / collect / swap / approve / bridge) | ❌ 没发 |
| 写 production positions | ❌ 没写 |
| 接 paid RPC / paid indexer | ❌ 没接 (solana publicnode + bsc-dataseed 是 free public) |
| 修改 r0 collector / r0 adapters | ❌ 没改 |
| 修改任何 12h data dir | ❌ 没改 |
| 写真实 secret | ❌ 没写 |
| merge dev/main | ❌ 没 merge |

**forbidden_actions_still_zero = true** ✅

## 7. Recommended next stage

**`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`**

理由:
1. 真实数据 (11h 5m of solana+bsc pool/quote/fee/liquidity/regime/candidate observations) 是 OK 的, 但窗口太短, 不能 promote 为 edge.
2. supervisor 循环拓扑有结构性 off-by-one, 12h 这个名字 misleading. 修这个要重新设计 supervisor (13 iterations 或 first-sleep-first-collect), 这超出本阶段范围 (本阶段是 read-only review).
3. R2 (actual fee accrual) 仍 LOCKED, 需要 freeze reopen 才能进入.
4. 没有证据值得 auto-advance.
5. user spec: "duration < 43200s ⇒ status MUST NOT be PASS" — 当前 status=PARTIAL, 正确, 不应升级.

## 8. 总结

- **artifacts 诚实**: ✅
- **数据真实**: ✅ (solana+bsc 真实 chain data, 156 r1_* files, no placeholders, no estimated baseline)
- **no fabrication / no compress / no short script / no old data mixed**: ✅
- **duration 真实 < 43200s, honest verdict PARTIAL**: ✅
- **forbidden actions 全 0**: ✅
- **edge_proven=no, can_run_probe_now=false, tiny_canary_allowed=no**: ✅ (LOCKED maintained)
- **本审查 status=WARN**: artifacts 正确, 跑得诚实地不够 12h.
- **不升级到 PASS**: ✅
- **不进入 R2 / probe / canary / live / paper / testnet**: ✅
- **不真实下单 / 不连 wallet / 不改 SDK adapter**: ✅

**Final**: WARN, no upgrade, no edge claim, no stage advance. PAUSE per FINAL_VERDICT.json.
