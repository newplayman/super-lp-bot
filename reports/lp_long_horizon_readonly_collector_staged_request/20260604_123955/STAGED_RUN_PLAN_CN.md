# Stage C — Staged Run Plan (分阶段 Run 计划)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`

## 0. 改向声明

原 fix_repeat_v1 推荐的 `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1`
(一次性 7d 墙钟采集) 改为本轮的
`LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
(6 阶段递增式: 6h/12h/24h/48h/72h/7d).

**one_shot_7d_replaced = true**.

## 1. 6 阶段总览

| Stage | 时长 | 累计 | 起点 | 终点 | 决策点 | 自动晋级 |
|---|---|---|---|---|---|---|
| 1 | 6h | 6h | T0 | T0+6h | gate + manual | ❌ |
| 2 | 12h | 18h | T1_end | T1_end+12h | gate + manual | ❌ |
| 3 | 24h | 42h | T2_end | T2_end+24h | gate + manual | ❌ |
| 4 | 48h | 90h | T3_end | T3_end+48h | gate + manual | ❌ |
| 5 | 72h | 162h | T4_end | T4_end+72h | gate + manual | ❌ |
| 6 | 7d (168h) | 330h | T5_end | T5_end+168h | gate + manual | ❌ |

**first_stage = 6h** (本轮默认起步, 不直接 7d).
**auto_advance_allowed = false** (每阶段必须独立 gate + 独立 manual approval).
**manual_approval_required_each_stage = true**.

## 2. 阶段间晋级条件 (粗粒度)

每阶段结束后, 必须同时满足:

1. Stage Gate Rules (Stage D) 全部核心项 PASS 或 WARN_ACCEPTABLE
2. Final Verdict 已生成 (含本阶段所有字段)
3. 独立 Audit 已记录 (per STAGE_FINAL_VERDICT_TEMPLATE)
4. Manual Approval 已收到 (per STAGE_APPROVAL_TEMPLATES, 见 Stage E)
5. Runtime Budget 未超限 (per STAGE_RUNTIME_BUDGET, 见 Stage F)
6. Failure / Abort 报告 (如有) 已 fix 或 accept (per Stage G)

任一 FAIL → 走 fix_repeat 或 pause, **不得自动晋级**.

## 3. 阶段间晋级流程图

```
[Stage 1: 6h]
   ├─ gate PASS / WARN_ACCEPTABLE
   ├─ final_verdict generated
   ├─ audit recorded
   ├─ manual approval received (per Stage E 模板)
   └─ ALL → proceed to Stage 2

[Stage 2: 12h]
   └─ ... (same 5 conditions)

... 6 stages ...
```

## 4. 数据维度 (per stage)

每阶段都采集:
- pool_snapshots (1 sample / 30 min, 6h 跑 = 12 sample / pool × 5 pool = 60 records)
- quote_snapshots (1 sample / 5 min, 6h 跑 = 72 sample / pool × 5 pool × 6 notional = 2160 records)
- fee_velocity (15m / 1h / 6h 滚动)
- liquidity_distribution (1 sample / 30 min)
- market_regime (1 sample / 15 min, classifier 实时分类)
- actual_fee_accrual (R0 阶段仅 schema, R1 阶段填 actual)

每阶段末尾**不**自动晋级, runner 退出 + 写 final_verdict + 等 manual approval.

## 5. runtime 边界

| 维度 | 6h | 12h | 24h | 48h | 72h | 7d |
|---|---|---|---|---|---|---|
| 累计 sample 数 (per pool) | 12 | 24 | 48 | 96 | 144 | 336 |
| 累计 quote (per pool × 6 notional) | 432 | 864 | 1728 | 3456 | 5184 | 12096 |
| 估计 sqlite 大小 | 50KB | 100KB | 200KB | 400KB | 600KB | 1.4MB |
| 估计 jsonl 大小 | 200KB | 400KB | 800KB | 1.6MB | 2.4MB | 5.6MB |
| 估计 disk 累计 | 250KB | 500KB | 1MB | 2MB | 3MB | 7MB |
| public RPC rate limit (5 req / 10s) | 1080 calls/6h | 4320 calls/12h | 8640 calls/24h | 17280 calls/48h | 25920 calls/72h | 60480 calls/7d |
| 估算 429 风险 | low | low | medium | medium | high | high (需 paid RPC) |

注: 实际 disk / RPC 数字以 stage 跑出来为准. Stage F 给出更详细 budget.

## 6. 每阶段独立 final_verdict

每阶段结束后, runner 必须生成
`reports/lp_long_horizon_readonly_collector_<stage>_run/<run_id>/FINAL_VERDICT.json`
(独立路径, 独立 gate, 独立 manual approval).

## 7. 阶段间不允许的快捷

- ❌ 6h 跳过直接 12h
- ❌ 12h 跳过直接 24h
- ❌ 任何 stage 跳过下一 stage
- ❌ auto_advance (即使 gate 全 PASS, 仍需 manual approval)
- ❌ 同一 manual approval 覆盖多 stage
- ❌ 把 7d 当作 "必然终点" (48h / 72h 失败, 应回退到 fix_repeat)

## 8. 当前状态 (本轮)

- **staged_plan_ready = false** (本轮生成模板, 未进入实际 6h run)
- **stages = ["6h", "12h", "24h", "48h", "72h", "7d"]** (6 阶段)
- **first_stage = "6h"** (默认起步)
- **auto_advance_allowed = false**
- **manual_approval_required_each_stage = true**
- **tmux_template_generated = false** (本轮生成模板, 默认 disabled)
- **cron_enabled = false**
- **systemd_enabled = false**
- **daemon_started = false**
- **long_run_started = false** (本轮不启动任何 stage)

## 9. 下一阶段 (manual approval 后)

`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- 接收 manual approval (per Stage E 模板)
- 实装 paid_rpc_indexer (Stage H, 9 项 readiness 第 7 项)
- 启用 tmux 模板 (从 disabled 改 enabled)
- 不写 cron / systemd (本阶段仅 tmux 短期后台)

## 10. 结论

Staged run plan 6 阶段, first_stage=6h, auto_advance=false, manual_approval 每阶段必须.
本轮不启动任何 stage, 仅生成模板. Stage C 通过. 进入 Stage D (Gate rules).
