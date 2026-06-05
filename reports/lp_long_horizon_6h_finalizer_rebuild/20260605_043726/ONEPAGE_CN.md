# LP Long Horizon 6h Finalizer Rebuild — One-Pager

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_043726`
- corrected_at_utc: `2026-06-05T14:10:32Z`

## 0. 一句话

V2 supervisor post-6h block 失败 (trap EXIT rc=1), fail-safe trap 写 default-zero FAIL FINAL_VERDICT, 覆盖了真实数据. 本 rebuild 脚本从 6 个 checkpoint dir 重建正确 verdict, 写到新路径, **不**覆盖 V2 原始 FAIL verdict.

## 1. 关键字段

| 字段 | V2 FINAL_VERDICT | CORRECTED |
|---|---|---|
| actual_runtime_minutes | 360 | 360 |
| actual_runtime_valid_for_6h_gate | true | true |
| short_mode_used | false | false |
| status | FAIL | **PASS** |
| gate_pass | false | **true** |
| selected_pool_count | 0 | **5** |
| pool_snapshot_rows | 0 | **5** |
| quote_snapshot_rows | 0 | **180** |
| fee_velocity_rows | 0 | **150** |
| liquidity_distribution_rows | 0 | **30** |
| market_regime_rows | 0 | **42** |
| can_advance_to_12h | false | **false** (LOCKED) |
| can_run_probe_now | false | **false** (LOCKED) |
| tiny_canary_allowed | "no" | **"no"** (LOCKED) |
| edge_proven | "no" | **"no"** (LOCKED) |
| wallet_or_tx_touched | false | **false** (LOCKED) |
| transaction_sent | false | **false** (LOCKED) |
| recommended_next_stage | FIX_REPEAT | **LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1** |

## 2. 重建方法

读 data_dir 6 个 checkpoint dir, dedup 聚合 row counts (per pool_address, per (pool_address, notional, quote_at)). 与 V2 supervisor Stage 3 aggregate logic 相同.

## 3. safety 字段 (LOCKED)

- can_run_probe_now: false
- tiny_canary_allowed: "no"
- edge_proven: "no"
- wallet_or_tx_touched: false
- transaction_sent: false
- auto_advance_started: false
- longer_stage_started: false
- do_not_auto_start_12h: true
- manual_approval_required_for_12h: true

## 4. 不覆盖原始 V2 FINAL_VERDICT

V2 FINAL_VERDICT (FAIL, default zeros) 保留在 `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json`, 本 rebuild 输出在 `reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726/`.
