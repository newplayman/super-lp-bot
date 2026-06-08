# R1 12h Full Wallclock — Reopen Conditions (CN)

- **stage**: `LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1`
- **status**: PAUSED
- **source_run_id**: 20260607_191500
- **review_commit**: b46f52e

## 0. 一句话

R1 12h full wallclock research thread 当前 **PAUSED**. 任何 reopen **必须**满足以下**全部**硬条件 + 软条件. 本文档是 reopen 的 gate, 不是建议; 不满足的 stage 不应被启动.

## 1. 硬条件 (Hard conditions, ALL must be satisfied)

### HC-1: User explicit reopen

- 用户必须在 conversation 中**显式**说 "reopen R1 12h full wallclock" 或等价表述
- "reopen" 不能从 PAUSE record 本身推断
- 没有 explicit 授权, 任何 stage 都不应被启动
- 即便 supervisor fix code PR 合入, 也不自动 reopen R1 12h research thread

### HC-2: User must redefine 12h full wallclock semantics

当前 `12h full wallclock` 在 R1 12h v3 中被定义为:
- 12 checkpoints
- 3600s sleep between checkpoints
- start-anchored loop, first collect at t=0
- scheduler_mode = `completion_anchored_sleep_3600`

**但这个定义在拓扑上必然只跑到 (N-1)*S + overhead ≈ 11h**, 不到 12h. 这是 v3 PARTIAL 的**结构性根因**.

Reopen 时, user 必须重新定义 12h 语义, 候选方案 (见 `SUPERVISOR_FIX_OPTIONS_CN.md`):
- **Fix A: 13 iterations** — 跑 13 个 collect, 第 13 次在 t≈12h 时 collect 后立即退出
- **Fix B: sleep-first-collect** — 第一次 collect 推迟到 t=S (= 3600s), 之后正常 11 次 sleep+collect
- **Fix C: start_ts_anchored scheduler mode** — 改用 `start_ts_anchored_interval_3600` (在 WALLCLOCK_PROOF 中作为 allowed_scheduler_modes 存在, 但 v3 未使用)

User 必须**显式**选择 fix path. 不允许 "try as-is again and see" — 那样只会再得到一次 PARTIAL.

### HC-3: Supervisor fix must be code-changed and merged

- 选择 fix path 后, 必须**实际改 code**:
  - `scripts/run_lp_long_horizon_r1_12h_stage_once.sh` (supervisor 循环)
  - `scripts/run_lp_long_horizon_r1_12h_full_wallclock.sh` (wrapper, 可能需要传新参数)
  - 或者 collector 中的 `scheduler_mode` 选择
- 修改必须经过 `make lint` + `make test` + CI
- 修改必须以新 commit 落到 `feat/supabase-postgres-deployment` (或 main, 视 user 决策)
- **不允许**在不开新 commit 的情况下声称 "supervisor 已修"

### HC-4: New stage must produce duration >= 43200s

新 stage (e.g. `LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V2`) 必须:
- `duration_wallclock_seconds >= 43200` (= 12h)
- 12/12 checkpoints 全部有真实数据
- max_checkpoint_interval_drift_seconds ≤ 200
- compressed=false, short_supervisor_used=false, full_supervisor_used=true
- finalize_after_expected_end=true
- artifacts 全部自洽 (typo-free, no placeholders, no estimated baseline, no old data mixed)
- forbidden_actions_still_zero=true
- 27 consistency checks 全部 pass
- WALLCLOCK_PROOF.duration_wallclock_seconds_ok=true
- FINAL_VERDICT.status=PASS

### HC-5: Even on PASS, R2 entry still requires separate freeze reopen

- R1 12h v3 PASS **不**自动 unlock R2
- R2 (actual fee accrual) 仍 LOCKED (`actual_fee_data_available=false`, `fee_proxy_only=true`)
- R2 entry 需要 user 显式 reopen freeze, 并在 conversation 中明确 "reopen R2 freeze"
- 不允许 "R1 PASS ⇒ R2" 的隐式 chain
- R2 entry 的 stage (e.g. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1`) 需要独立 artifacts 链

### HC-6: Edge claim requires R2 actual fee data, not R1 alone

- edge_proven=yes 需要 **actual fee accrual data**, 来自 R2
- R1 12h (即使 PASS) 仍只是 **observation window**, 不足以 claim edge
- fee_proxy_only=true 期间, 任何 "edge proven" 声明是 invalid
- v3 review 明确: r1_data_observational_value=yes_but_not_edge, r1_data_reuse_recommendation=may be reused as real-data observation window, not edge

## 2. 软条件 (Soft conditions, recommended)

### SC-1: Engineering mainline first

- 在 R1 reopen 之前, 推荐**先**完成 `P0_FIX_POSTGRES_SHADOW_DEPLOYMENT_V1` (per `NEXT_ENGINEERING_TRACK_RECOMMENDATION.md`)
- 这意味着 shadow deployment 可运行, CI/migration tests 更强, R2 才有更稳的基础
- 但 SC-1 **不是** hard blocker; user 可优先 reopen R1

### SC-2: Source health review before next 12h

- v3 期间 base RPC 全部 403 (`chains_skipped=["base"]`), universe 限于 solana+bsc
- 下一次 12h 之前, 推荐评估 base RPC 是否可用 (考虑 paid RPC 或换 endpoint), 或明确接受 "no-base 12h" 作为新的 partial universe
- 不需要 base 必须通, 但需要**显式**声明

### SC-3: Multi-run 12h+ for confidence

- 单次 12h full wallclock PASS 仍是 single sample
- 如果目标是 higher confidence, 推荐**多次** 12h (e.g. 3 consecutive 12h runs), 每次 ckpt count 12
- 但这超出"单次 12h"语义, 属于不同的 stage design, 需 user 显式批准

### SC-4: Documentation of "what edge signal would look like"

- 在 reopen R1 / 启动 R2 之前, 推荐**先**文档化 "什么算 edge signal" (具体数值 / 跨多次 run 的一致性要求)
- 当前 LP strategy research 是 FROZEN, 没有定义 "edge"
- 不定义 edge 而先 claim pass 是 risk

## 3. Reopen procedure (建议步骤, 不强制)

如果 user 决定 reopen, 推荐的 stage 序列:

1. **`LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REOPEN_PLAN_V1`** (新 stage)
   - 重述 fix path (HC-2)
   - 列出新 stage 设计 (HC-4)
   - 列出与 v3 的差异 (supervisor change + duration target)
   - 列出 R2 仍 LOCKED 的明示
   - 列出 forbidden actions 仍 maintained
2. **Supervisor fix code PR** (新 commit, 经过 CI)
3. **`LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V2`** (新 stage, 实际重跑)
   - duration_wallclock_seconds >= 43200
   - 12/12 ckpt 全部真实
   - artifacts 自洽
4. **`LP_LONG_HORIZON_R1_12H_FULL_WALLCLOCK_REPEAT_V2_REVIEW_V1`** (新 stage, 复核)
5. **如果 v2 PASS**: R1 12h thread 可以从 PAUSED → PASSED. **不**自动 R2.
6. **如果 v2 仍 PARTIAL 或 FAIL**: 回到 step 2, 重新 fix supervisor.

## 4. R2 reopen 是独立流程

R2 entry 流程**不**在本 reopen 范围:
- R2 需要 `actual_fee_data_available=true` (现在 false)
- R2 需要 `fee_proxy_only=false` (现在 true)
- R2 需要 freeze reopen (现在 LOCKED)
- R2 stage 命名空间独立 (e.g. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1`)

不要在本 record 中隐式 unlock R2. R2 reopen 是 user 在**另一个 conversation turn** 的独立决策.

## 5. 一句话

R1 12h full wallclock **PAUSED**. Reopen 需要: user explicit + 12h semantics 重定义 + supervisor code change + new stage 跑到 duration>=43200 + artifacts 自洽 + R2 仍独立 reopen. 即使 R1 PASS, R2 仍 LOCKED. 严禁隐式 chain.
