# Corrected 6h Run Summary (重建自 checkpoint)

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_043726`
- source_verdict_path: `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json`
- source_verdict_status: **FAIL** (supervisor_finalize_failed=True)
- corrected_at_utc: `2026-06-05T14:10:32Z`

## 0. 一句话

从 data_dir **重建** 6h row counts. V2 supervisor post-6h block 失败 (`trap EXIT rc=1`), fail-safe trap 写了 default-zero FAIL verdict, 覆盖了即将写入的真实数据. 本 rebuild 脚本从 6 个 checkpoint dir 重新聚合, 得到真实 row counts.

## 1. 实际运行时间

- actual_runtime_minutes: **360**
- expected_min_runtime_minutes: 330
- actual_runtime_valid_for_6h_gate: **true**
- short_mode_used: **false**

## 2. row counts (rebuilt from data_dir)

| 类别 | count |
|---|---|
| selected_pool_count | 5 |
| pool_snapshot_rows | 5 |
| quote_snapshot_rows | 180 |
| fee_velocity_rows | 150 |
| liquidity_distribution_rows | 30 |
| market_regime_rows | 42 |
| actual_fee_accrual_placeholder_rows | 6 |

## 3. safety 字段 (LOCKED)

- wallet_or_tx_touched: **false**
- transaction_sent: **false**
- no_production_write: **true**
- no_shadow_overwrite: **true**
- can_run_probe_now: **false**
- tiny_canary_allowed: **"no"**
- send_hard_disable_still_active: **true**
- auto_advance_started: **false**
- longer_stage_started: **false**

## 4. checkpoint 状态

6 个 checkpoint 全部存在, 全部含 7 文件 (pool/quote/fee/liq/regime/actual_fee/summary).

## 5. 重建方法

读 data_dir 6 个 checkpoint dir, dedup 聚合 row counts (per pool_address, per (pool_address, notional, quote_at)). 与 V2 supervisor Stage 3 aggregate logic 相同.

## 6. 与 V2 FINAL_VERDICT 差异

| 字段 | V2 FINAL_VERDICT | CORRECTED |
|---|---|---|
| status | FAIL | PASS |
| selected_pool_count | 0 | 5 |
| pool_snapshot_rows | 0 | 5 |
| quote_snapshot_rows | 0 | 180 |
| fee_velocity_rows | 0 | 150 |
| liquidity_distribution_rows | 0 | 30 |
| market_regime_rows | 0 | 42 |
| gate_pass | false | true |
