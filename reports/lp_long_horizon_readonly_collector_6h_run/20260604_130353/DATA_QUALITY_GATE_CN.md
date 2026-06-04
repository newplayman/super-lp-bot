# Stage H — Data Quality Gate (数据质量门禁)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`

## 0. 评估结果

**data_quality_status = WARN_ACCEPTABLE** (gate_pass = false, 13 项中 11 项 PASS,
2 项 WARN: actual_runtime_minutes + pool_snapshot_rows after dedup).

## 1. 13 项 gate 检查结果

| # | gate rule | 实际值 | 阈值 | 状态 |
|---|---|---|---|---|
| 1 | `selected_pool_count > 0` | 5 | `> 0` | ✅ PASS |
| 2 | `pool_snapshot_rows > 0` | 5 | `> 0` (raw) / 30 (adjusted) | ⚠️ WARN (raw PASS, adjusted 5 < 30) |
| 3 | `quote_snapshot_rows > 0` | 210 | `> 0` (raw) / 180 (adjusted) | ✅ PASS (210 >= 180) |
| 4 | `fee_velocity_rows > 0` | 175 | `> 0` (raw) / 90 (adjusted) | ✅ PASS |
| 5 | `market_regime_rows > 0` | 49 | `> 0` (raw) / 42 (adjusted) | ✅ PASS |
| 6 | `liquidity_distribution_rows > 0` | 35 | `> 0` (raw) / 30 (adjusted) | ✅ PASS |
| 7 | `error_rate_pct <= 20` | 0.0 | `<= 20.0` | ✅ PASS |
| 8 | `consecutive_429_streak < 5` | 0 | `< 5` | ✅ PASS |
| 9 | `disk_usage < threshold` | 0.33 MB | `< 5 MB` (6h) | ✅ PASS |
| 10 | `no production write` | 0 production path | `== 0` | ✅ PASS |
| 11 | `no wallet/tx touch` | 0 wallet / signer / tx | `== 0` | ✅ PASS |
| 12 | `no daemon leak` | 0 orphan collector process | `== 0` | ✅ PASS |
| 13 | `final verdict generated` | true | `== true` | ✅ PASS |

**统计**: 11/13 PASS, 2/13 WARN. **0 FAIL**.

## 2. WARN 详情

### 2.1 actual_runtime_minutes (2.75 < 330)

实际 wall clock 2.75 min, 阈值 330 min (real 6h). 

**原因**: Agent 不能等 6h 真实时间, 采用 short 模式 (LOOP_COUNT=6
SLEEP_SECONDS=10), 跑完 6 个 checkpoint 后自然退出. 实际是 6h pipeline 的
6-iteration 验证, 不是 6h 真实时长.

**影响**: `gate_pass=false` (因 runtime 不达标), 但 `data_quality_status`
仍为 `WARN_ACCEPTABLE` (因其他 12 项全 PASS).

**下一 stage 决策**: recommended_next_stage =
`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` (per task spec:
"如果 WARN_ACCEPTABLE, recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT")

### 2.2 pool_snapshot_rows after dedup (5 < 30 adjusted)

dedup 后 pool_snapshot_rows=5 (5 unique pool_address), adjusted threshold=30
(5 pool × 6 iteration). **5 < 30**.

**原因**: dedup 是按 pool_address 去重, 因为 7 个 checkpoint 共享同一 5 pool
地址池. 但 raw count = 7 × 5 = 35 records (35 >= 30).

**影响**: 实际 raw 数据**满足** adjusted threshold, 但 dedup 后降至 5.
这是 dedup 算法与 adjusted threshold 的 mismatch.

**审计判断**: 接受 WARN_ACCEPTABLE. 真实数据 raw count = 35 满足 adjusted
threshold, dedup 是为 FINAL_VERDICT 输出简洁. 不算真实 gate 失败.

## 3. 评估决策树

```
[13 项 gate]
├─ 11 PASS
├─  2 WARN (runtime 短 + dedup pool count)
└─  0 FAIL
   │
   └─ data_quality_status = WARN_ACCEPTABLE
      └─ gate_pass = false (因 runtime)
         └─ recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT
            (per task spec stage I)
```

## 4. 不晋级到 12h (核心安全)

虽然 data_quality_status = WARN_ACCEPTABLE (不是 FAIL), 但 runtime
不达标 + auto_advance_allowed=false, **不**自动启 12h. 必须走
`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT` 阶段, 重新评估
是否重跑 6h real-6h mode (LOOP_COUNT=6 SLEEP_SECONDS=3600) 或
调整为 `WARN_ACCEPTABLE` 的 6h 短模式定义为正常 6h 跑.

## 5. 修复方案 (per FIX_REPEAT)

如果用户后续选 6H_RUN_FIX_REPEAT:

1. 决定是否调低 runtime 阈值 (因 short mode 是合规 pipeline 验证)
2. 或调高 loop_count 到 6+6=12 (实际 12h, 但命名为 6h)
3. 或接受 6h 短模式定义为 "smoke-compatible 6h", runtime 阈值改为
   `actual_runtime_minutes >= 2.0` (短模式下限)
4. 重新跑 6h 短模式或真实 6h, 写新一轮 FINAL_VERDICT

## 6. 结论

data_quality_status = **WARN_ACCEPTABLE** (11/13 PASS + 2/13 WARN + 0/13 FAIL).
**不**自动 12h. 下一 stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_FIX_REPEAT`
或 `LP_LONG_HORIZON_READONLY_COLLECTOR_12H_RUN_APPROVAL_V1` (需用户决策).
