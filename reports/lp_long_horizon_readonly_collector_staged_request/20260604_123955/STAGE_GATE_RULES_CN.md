# Stage D — Stage Gate Rules (阶段门禁规则)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_STAGED_RUN_REQUEST_V1`
- run_id: `20260604_123955`

## 0. 目的

定义 6 阶段 (6h/12h/24h/48h/72h/7d) 各自的 gate 规则. 每阶段结束时, runner
**必须**逐项检查. 任一核心项 FAIL → 不进入下一阶段 → 走 fix_repeat 或
pause. 不得自动重跑.

## 1. 通用 13 项 gate 规则 (per stage)

每阶段都跑这 13 项检查:

| # | 检查项 | 阈值 | 评估级别 |
|---|---|---|---|
| 1 | `selected_pool_count > 0` | `> 0` | **核心** |
| 2 | `pool_snapshot_rows > 0` | `> 0` | **核心** |
| 3 | `quote_snapshot_rows > 0` | `> 0` | **核心** |
| 4 | `fee_velocity_rows > 0` | `> 0` | **核心** |
| 5 | `market_regime_rows > 0` | `> 0` | **核心** |
| 6 | `error_rate_pct <= 20` | `<= 20.0` | **核心** |
| 7 | `consecutive_429_streak < 5` | `< 5` | **核心** |
| 8 | `disk_usage below threshold` | `< 100MB` (per stage 估计) | **核心** |
| 9 | `no production write` | 0 production path | **核心** |
| 10 | `no wallet/tx touch` | 0 wallet / signer / tx 调用 | **核心** |
| 11 | `no daemon leak` | runner 进程数 == 1 (无 leak) | **核心** |
| 12 | `final verdict generated` | FINAL_VERDICT.json 存在 | **核心** |
| 13 | `data_quality_status` | PASS / WARN_ACCEPTABLE | **核心** |

13 项全部为**核心** (任一 FAIL 都阻断晋级).

## 2. 阶段特化阈值

| 阈值 | 6h | 12h | 24h | 48h | 72h | 7d |
|---|---|---|---|---|---|---|
| minimum_pool_snapshot_rows | 60 | 120 | 240 | 480 | 720 | 1680 |
| minimum_quote_snapshot_rows | 2160 | 4320 | 8640 | 17280 | 25920 | 60480 |
| minimum_fee_velocity_rows | 20 | 40 | 80 | 160 | 240 | 560 |
| minimum_liquidity_distribution_rows | 12 | 24 | 48 | 96 | 144 | 336 |
| minimum_market_regime_rows | 24 | 48 | 96 | 192 | 288 | 672 |
| minimum_real_data_pct | 80% | 80% | 80% | 80% | 80% | 80% |
| error_rate_pct_max | 20 | 20 | 20 | 20 | 20 | 20 |
| consecutive_429_streak_max | 5 | 5 | 5 | 5 | 5 | 5 |
| disk_usage_max_mb | 1 | 2 | 5 | 10 | 15 | 30 |
| production_write_count_max | 0 | 0 | 0 | 0 | 0 | 0 |
| wallet_tx_touch_count_max | 0 | 0 | 0 | 0 | 0 | 0 |
| daemon_leak_count_max | 0 | 0 | 0 | 0 | 0 | 0 |
| final_verdict_required | true | true | true | true | true | true |
| data_quality_status_required | PASS / WARN_ACCEPTABLE | | | | | |

## 3. 评估级别

| 状态 | 含义 | 晋级策略 |
|---|---|---|
| `PASS` | 13 项全部满足 | 走 manual approval → 下一 stage |
| `WARN_ACCEPTABLE` | 13 项满足, 但有 < 3 项低优 warning (e.g. disk 80% 满) | 走 manual approval → 下一 stage (但 audit 必须记录 warning) |
| `FAIL` | 任一核心项不满足 | **不晋级**, 走 fix_repeat 或 pause, 不自动重跑 |

## 4. FAIL 时的禁止

任一核心项 FAIL:

- ❌ 不进入下一阶段
- ❌ 不自动重跑当前阶段
- ❌ 不修改 9 项 readiness 状态
- ❌ 不写 production 表
- ✅ 输出 `LP_LONG_HORIZON_READONLY_COLLECTOR_<STAGE>_RUN_FAILURE_<RUN_ID>/`
  子报告 (含 fix_repeat / pause 决策依据)
- ✅ 写 FINAL_VERDICT.json with `data_quality_status=FAIL`
- ✅ 走 Stage G 失败 / abort policy

## 5. data_quality_status 决策树

```
[13 项 gate]
   ├─ 13/13 PASS → PASS
   ├─ 12-13 项 PASS, 0-1 WARN → WARN_ACCEPTABLE
   ├─ 11 项 PASS, 2+ WARN → WARN_ACCEPTABLE (需 audit 接受)
   └─ < 11 项 PASS 或任一核心 FAIL → FAIL
```

注: 13 项核心, 任何一项 FAIL 即 FAIL. WARN 是"pass 但有 sub-warning" 的状态,
不是"fail 但 accept" 的状态.

## 6. 阶段晋级条件 vs 阶段 gate 关系

- 阶段 gate (Stage D) 是"当前 stage 完成" 的判定
- 阶段晋级 (Stage C) 包含 6 个条件: gate + final_verdict + audit + manual_approval +
  runtime_budget + failure_policy

任一晋级条件 FAIL → 不晋级, 走 fix_repeat / pause.

## 7. 实施位置

每阶段结束时, runner 跑以下命令 (per STAGE_GATE_CHECK_TEMPLATE, 本阶段生成):

```bash
python3 scripts/check_stage_gate.py \
  --stage <STAGE> \
  --run-id <RUN_ID> \
  --data-dir data/lp_long_horizon/<RUN_ID>/<STAGE>_run \
  --output reports/lp_long_horizon_readonly_collector_<STAGE>_run/<RUN_ID>/STAGE_GATE_RESULT.json
```

(本轮不实装 check_stage_gate.py, 仅生成模板. 6H_RUN_APPROVAL_V1 阶段实装.)

## 8. 13 项 gate 输出格式

```json
{
  "stage": "6h",
  "run_id": "20260604_XXXXXX",
  "evaluated_at": "ISO 8601 UTC",
  "checks": [
    {"name": "selected_pool_count_gt_zero", "value": 5, "threshold": "> 0", "pass": true},
    {"name": "pool_snapshot_rows_gt_zero", "value": 60, "threshold": "> 0", "pass": true},
    {"name": "quote_snapshot_rows_gt_zero", "value": 2160, "threshold": "> 0", "pass": true},
    {"name": "fee_velocity_rows_gt_zero", "value": 20, "threshold": "> 0", "pass": true},
    {"name": "market_regime_rows_gt_zero", "value": 24, "threshold": "> 0", "pass": true},
    {"name": "error_rate_pct_le_20", "value": 0.5, "threshold": "<= 20.0", "pass": true},
    {"name": "consecutive_429_streak_lt_5", "value": 0, "threshold": "< 5", "pass": true},
    {"name": "disk_usage_below_threshold", "value": 0.25, "threshold": "< 1MB", "pass": true},
    {"name": "no_production_write", "value": 0, "threshold": "== 0", "pass": true},
    {"name": "no_wallet_tx_touch", "value": 0, "threshold": "== 0", "pass": true},
    {"name": "no_daemon_leak", "value": 0, "threshold": "== 0", "pass": true},
    {"name": "final_verdict_generated", "value": true, "threshold": "== true", "pass": true},
    {"name": "data_quality_status", "value": "PASS", "threshold": "PASS or WARN_ACCEPTABLE", "pass": true}
  ],
  "pass_count": 13,
  "warn_count": 0,
  "fail_count": 0,
  "data_quality_status": "PASS",
  "advance_allowed": true,
  "next_action": "wait_for_manual_approval"
}
```

## 9. 阶段间 13 项 gate 一致性

6 阶段**完全用同一份** 13 项 gate 规则, 仅阶段特化阈值 (row 数 / disk 上限) 不同.
也就是说, gate 规则本身**不**因 stage 长度变化, 只因数据量变化.

这是 fix_repeat 友好: 任何 stage FAIL, 修复后可重新跑同一 stage (不需重新设计 gate).

## 10. 结论

13 项 gate 规则 + 6 阶段特化阈值 + 3 状态 (PASS / WARN_ACCEPTABLE / FAIL) +
阶段晋级条件. 任一核心 FAIL → 走 fix_repeat / pause. Stage D 通过. 进入
Stage E (审批短语模板).
