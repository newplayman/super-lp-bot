# Corrected Data Quality Gate (重建自 checkpoint)

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_043726`

## 0. 评估结果

data_quality_status = **PASS** (13 PASS, 0 FAIL)
gate_pass = **true**
can_advance_to_12h = **false** (LOCKED, 不自动 12h)

## 1. 13 项 gate 检查

| gate | 状态 |
|---|---|
| actual_runtime_minutes_ge_330 | ✅ |
| short_mode_used_false | ✅ |
| selected_pool_count_gt_zero | ✅ |
| pool_snapshot_rows_gt_zero | ✅ |
| quote_snapshot_rows_gt_zero | ✅ |
| fee_velocity_rows_gt_zero | ✅ |
| liquidity_distribution_rows_gt_zero | ✅ |
| market_regime_rows_gt_zero | ✅ |
| error_rate_pct_le_20 | ✅ |
| consecutive_429_max_lt_5 | ✅ |
| no_wallet_tx_touch | ✅ |
| no_production_write | ✅ |
| no_shadow_overwrite | ✅ |

## 2. 决策

- data_quality_status: **PASS**
- gate_pass: true
- can_advance_to_12h: **false** (不自动 12h, 需用户单独审批)
