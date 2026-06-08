# R1 12h Full Wallclock — Next Stage Recommendation

- **reviewed_run_id**: `20260607_191500`
- **current_stage**: `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` (this review)
- **source_stage_verdict**: `PARTIAL_WALLCLOCK_FAIL_NEEDS_USER_DECISION` (honest)
- **review_verdict**: **WARN** (artifacts honest, run did not reach 12h, no edge claim)

## 1. 推荐的 next stage

**`PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`**

(per source `FINAL_VERDICT.recommended_next_stage`)

## 2. 4 个 allowed next stages (per source FINAL_VERDICT)

| Stage | 描述 | 推荐? | 理由 |
|---|---|---|---|
| `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` | 12h node report review (本阶段) | **已完成** ✅ | read-only review, 0 数据采集, 0 代码改动 |
| `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` | 修 R1 collector 然后重跑 12h full wallclock | ❌ 不推荐 | 修 collector 改 code, 违反 no-touch invariant; 修 supervisor 循环拓扑需要 user spec 重新定义 12h 的语义 (13 iterations 或 first-sleep-first-collect) |
| `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` | R2 (actual fee accrual) | ❌ **LOCKED** | requires freeze reopen, 不在 R1 阶段授权范围 |
| `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` | 暂停自动化 LP probe, 收集 longer-horizon data | ✅ **推荐** | 不动 code, 不动 freeze, 不 probe / canary / live; 给 user 时间重新评估 supervisor 设计 |

## 3. 选 PAUSE 的具体理由

### 3.1 真实数据价值

- 11h 5m 的 solana+bsc 真实 pool/quote/fee/liquidity/regime/candidate observations 是有 observational 价值的
- 156 r1_* data files, 6 dim row counts consistent across 12 ckpts (20/120/100/20/2/20)
- watchlist 稳定 7 → 7 (无漂移)
- 但 **fee_proxy_only=true**, actual fee data 仍 unavailable
- 11h 窗口太短, 不能 claim edge. 但也不是 noise — 是合理 observation window

### 3.2 拓扑结构性问题需要 user 决策

supervisor 的循环设计 (N=12 iterations, sleep=3600, start-anchored) 决定了 12h "full wallclock" 在当前代码下永远只能跑到 ~11h. 三种 fix 路径都涉及改 code:

- **fix A**: 改 supervisor 跑 13 iterations
- **fix B**: 改 supervisor 第一次 sleep 3600s 后再 collect
- **fix C**: 改用 `start_ts_anchored_interval_3600` scheduler mode

这些改动:
- 需要 user 重新定义 "12h full wallclock" 的语义
- 不在 read-only review 范围内
- 任何新一轮 12h 都属于新 stage, 需 user explicit 授权

### 3.3 R2 仍 LOCKED

- `actual_fee_data_available=false` (LOCKED)
- `fee_proxy_only=true` (LOCKED)
- R2 entry 需要 freeze reopen
- 当前 stage 是 R1 阶段, R2 跨越阶段不允许

### 3.4 No-touch invariant 维持

本阶段 (review) 完全 read-only:
- 不修改 collector (`internal/core/scanner/`, `scripts/lp_*real_data_collector*`)
- 不修改 adapters (`internal/adapters/pool/*`, `internal/adapters/store/*`)
- 不修改 runner / supervisor (`scripts/run_lp_long_horizon_r1_12h_*.sh`)
- 不修改 任何 12h data dir
- 不进入 24h / 48h / 72h / 7d
- 不 probe / canary / live / paper
- 不连 wallet
- 不发 tx

## 4. 推荐的 follow-up (when user reopens)

如果 user 后续决定继续, 推荐的 follow-up order:

1. **重新定义 12h full wallclock 的语义** (user spec) — 决定 fix A / B / C, 或者重新定义 N=12 → N=13
2. **改 supervisor** (`scripts/run_lp_long_horizon_r1_12h_stage_once.sh` + wrapper) — 这是 code change, **不在本 stage**
3. **重跑 12h full wallclock** with 修正后 supervisor — 新 stage `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V2`
4. **如果 v2 duration ≥ 43200s 且 ckpt_count=12/12**, then status=PASS, 但仍 NOT 进入 R2 (R2 需 freeze reopen)
5. **如果 v2 仍 duration < 43200s**, then 升级为 fail-closed, 进一步分析

## 5. 不推荐做的事情

- ❌ 升级 R1 status 到 PASS
- ❌ 声明 edge_proven=yes
- ❌ 进入 R2 (LOCKED, needs freeze reopen)
- ❌ probe / canary / live / paper
- ❌ 修改 collector / adapters / supervisor (no-touch invariant)
- ❌ 重新跑 12h without user spec change
- ❌ 进入 24h / 48h / 72h / 7d (LOCKED)
- ❌ merge dev / main
- ❌ 使用 pkill -f

## 6. 一句话

推荐 **PAUSE**. v3 跑得诚实, 数据真实, 但 duration 不达标是 supervisor 循环拓扑结构性的, 需要 user 重新定义 12h 语义并改 supervisor code, 这超出 read-only review 范围. R2 仍 LOCKED. No edge claim. No probe. No auto-advance. No touch.
