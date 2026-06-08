# R1 12h Full Wallclock — PAUSE Decision (CN)

- **stage**: `LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1`
- **status**: **PAUSED**
- **source_run_id**: `20260607_191500`
- **source_status**: `PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION`
- **review_commit**: `b46f52e` (LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1, status=WARN)
- **branch**: `feat/supabase-postgres-deployment`
- **recorded_at_utc**: `2026-06-08T18:50:00Z`

## 0. 一句话

R1 12h full wallclock v3 (RUN_ID `20260607_191500`) 跑得诚实, 但 `duration_wallclock_seconds=39917 < 43200s`, status=PARTIAL. 根因是 **supervisor 循环拓扑结构性的 off-by-one** (12 ckpt × ~3600s sleep + first-collect-at-t0 → 11h 5m, 永远 < 12h). node report review (commit `b46f52e`) 确认 status=WARN. 本阶段**正式 PAUSE R1 12h full wallclock research thread**, 固化为 artifacts, 不动 code, 不动 data, 不动 freeze, 不 auto-advance, 不 probe / canary / live / R2.

## 1. PAUSE 决策来源

| 来源 | 值 |
|---|---|
| source `FINAL_VERDICT.json` (R1 12h v3) | `recommended_next_stage: "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA"` |
| review `FINAL_REVIEW_VERDICT.json` (`b46f52e`) | `recommended_next_stage: "PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA"` |
| **本 stage 决策** | **`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (confirmed)** |

## 2. PAUSE 的内容 (本 stage **不**做的事情)

- ❌ **不**重跑 12h (会得到同样的 PARTIAL)
- ❌ **不**启动 13h / 24h / 48h / 72h / 7d
- ❌ **不**进入 R2 (actual fee accrual, LOCKED)
- ❌ **不**probe / canary / live / paper
- ❌ **不**连 wallet / keypair / signer
- ❌ **不**发 transaction / mint LP NFT / add liquidity / remove / collect / swap / approve / bridge
- ❌ **不**接 paid RPC / paid indexer
- ❌ **不**写 production positions / 覆盖 shadow / overwrite 既有 data dir
- ❌ **不**写真实 secret / paid RPC key
- ❌ **不**merge main / dev
- ❌ **不**修改 collector / adapters / runner / supervisor code
- ❌ **不**修改任何 12h / 12h_compressed / smoke / v1_partial / v3 data dir
- ❌ **不**自动 24h / 不自动 R2
- ❌ **不**声称 edge_proven=yes
- ❌ **不**解锁 canary_allowed / tiny_canary_allowed
- ❌ **不**使用 pkill -f

## 3. PAUSE **做**的事情 (本 stage 的 deliverable)

| 任务 | 状态 |
|---|---|
| 正式关闭 R1 12h full wallclock research thread | ✅ status=PAUSED |
| 固化 PAUSE 决策为 artifacts (本目录 7 个文件) | ✅ |
| 保留所有 v3 source deliverables (13 个, read-only) | ✅ |
| 保留 11h 5m 真实 R1 observation data (data dir 不删不改) | ✅ |
| 保留 v0/v1/v2/old_12h data dir (no-touch invariant) | ✅ |
| 文档化 supervisor 3 个 fix 选项 (供 future reopen) | ✅ `SUPERVISOR_FIX_OPTIONS_CN.md` |
| 文档化哪些 data 可被 future re-aggregation 复用 | ✅ `WHAT_DATA_CAN_BE_REUSED_CN.md` |
| 文档化 REOPEN 条件 | ✅ `REOPEN_CONDITIONS_CN.md` |
| 把工程主线 redirect 到 `P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1` | ✅ `NEXT_ENGINEERING_TRACK_RECOMMENDATION.md` |
| 锁定 20 个 forbidden actions (含 `no_modify_v3_full_wallclock_data_dir_20260607_191500`) | ✅ `FORBIDDEN_ACTIONS_LOCK.json` |

## 4. 状态字段 (与 source 一致)

| 字段 | 值 | 备注 |
|---|---|---|
| status | PAUSED | 本 stage 引入 |
| source_run_id | 20260607_191500 | R1 12h v3 run |
| source_status | PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION | honest |
| review_commit | b46f52e | review status=WARN |
| duration_wallclock_seconds | 39917 | < 43200 |
| duration_wallclock_seconds_ok | false | honest |
| checkpoint_count | 12/12 | 12 个真实 ckpt |
| data_value | real_observation_only | 不是 edge, 不是 noise, 是真实 observation window |
| edge_proven | "no" | LOCKED |
| actual_fee_data_available | false | LOCKED |
| fee_proxy_only | true | LOCKED |
| can_run_probe_now | false | LOCKED |
| tiny_canary_allowed | "no" | LOCKED |
| r2_locked | true | LOCKED |
| supervisor_fix_required_before_repeat | true | 拓扑 off-by-one |
| no_auto_advance | true | 不进 24h / R2 |
| forbidden_actions_still_zero | true | 27 actions 全部 ok |
| recommended_next_engineering_track | P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1 | 工程主线 |

## 5. 历史 lineage (R1 12h thread 完整时间线)

| 日期 (UTC) | commit | 状态 | 说明 |
|---|---|---|---|
| 2026-06-04 | `7940cff` | research: final freeze lp research 20260604_051254 | 早 freeze |
| 2026-06-07 18:44Z | (v0) | exited (sed bug) | PID 2876054 |
| 2026-06-07 18:52Z | (v1) | PARTIAL_WALLCLOCK_FAIL (whitelist) | PID 2892835, RUN_ID 20260607_184500 |
| 2026-06-07 19:16Z | (v3 launch) | started | PID 2948793, RUN_ID 20260607_191500 |
| 2026-06-08 06:21Z | (v3 end) | 12/12 ckpt, duration 39917s | rc=0 |
| 2026-06-08 08:23Z | (verifier) | FINAL_VERDICT.json written | status=PARTIAL |
| 2026-06-08 18:30Z | `b46f52e` | review: status=WARN | review commit |
| **2026-06-08 18:50Z** | **(本 stage)** | **status=PAUSED** | **本 stage 引入** |

## 6. 关键 takeaway

- R1 12h v3 数据 **真实**, **不 fabrication**, supervisor **clean exit rc=0**
- duration < 12h 是 **supervisor 循环拓扑结构性**的, 不是 v3 run 错
- 修复需要改 code, 不在本 read-only PAUSE 范围
- 即使 v3 PASS, R2 仍需 freeze reopen
- PAUSE 决策: 暂停 R1 research thread, redirect engineering 到 P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1
- 所有 LOCKED fields 维持: edge_proven=no, can_run_probe_now=false, tiny_canary_allowed=no, r2_locked=true, no_auto_advance=true

## 7. 严禁 checklist (PAUSE 期间)

- [x] 24h / 48h / 72h / 7d: NOT STARTED
- [x] R2 (actual fee accrual): NOT ENTERED (LOCKED)
- [x] probe / canary / live / paper: NOT RUN
- [x] wallet / keypair / signer: NOT LOADED
- [x] tx send / mint / add / remove / collect / swap / approve / bridge: NOT SENT
- [x] paid RPC / paid indexer: NOT USED
- [x] production write / shadow overwrite: NOT DONE
- [x] real secret: NOT COMMITTED
- [x] merge main / dev: NOT DONE
- [x] supervisor / collector / adapter / runner code: NOT MODIFIED
- [x] 任何 12h / 12h_compressed / smoke / v1_partial / v3 data dir: NOT MODIFIED
- [x] edge_proven: STILL "no"
- [x] pkill -f: NOT USED
