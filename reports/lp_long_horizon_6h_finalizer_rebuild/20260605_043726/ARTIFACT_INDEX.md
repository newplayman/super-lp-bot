# ARTIFACT INDEX — Corrected 6h Verdict (Rebuild from Checkpoints)

- stage: `LP_LONG_HORIZON_6H_FINALIZER_REBUILD_FROM_CHECKPOINTS_V1`
- source_run_id: `20260605_043726`
- source_verdict: `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json`
- output_dir: `reports/lp_long_horizon_6h_finalizer_rebuild/20260605_043726`
- corrected_at_utc: `2026-06-05T14:10:32Z`

## 1. 11 个输出文件

- `CORRECTED_FINAL_VERDICT.json`
- `CORRECTED_SIX_HOUR_RUN_SUMMARY.json`
- `CORRECTED_SIX_HOUR_RUN_SUMMARY_CN.md`
- `CORRECTED_DATA_QUALITY_GATE.json`
- `CORRECTED_DATA_QUALITY_GATE_CN.md`
- `CORRECTED_MARKET_REGIME_SUMMARY.json`
- `CORRECTED_MARKET_REGIME_SUMMARY_CN.md`
- `CORRECTED_NEXT_STAGE_DECISION.json`
- `CORRECTED_NEXT_STAGE_DECISION_CN.md`
- `ONEPAGE_CN.md`
- `ARTIFACT_INDEX.md`

## 2. 关键数字

| 维度 | 值 |
|---|---|
| actual_runtime_minutes | 360 |
| actual_runtime_valid_for_6h_gate | true |
| short_mode_used | false |
| checkpoint_count | 6 |
| selected_pool_count | 5 |
| pool_snapshot_rows | 5 |
| quote_snapshot_rows | 180 |
| fee_velocity_rows | 150 |
| liquidity_distribution_rows | 30 |
| market_regime_rows | 42 |
| actual_fee_accrual_placeholder_rows | 6 |
| gate_pass | true |
| data_quality_status | PASS |
| gate_check_pass_count | 13 |
| gate_check_fail_count | 0 |
| can_advance_to_12h | false (LOCKED) |
| recommended_next_stage | LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1 |

## 3. 锁定字段 (5 项全 false/no)

| 字段 | 锁定值 |
|---|---|
| can_run_probe_now | false |
| tiny_canary_allowed | "no" |
| edge_proven | "no" |
| wallet_or_tx_touched | false |
| transaction_sent | false |

## 4. 严禁 (本轮全部不触发)

- 不启动 12h / 24h / 48h / 72h / 7d
- 不启动新 tmux / cron / systemd / daemon
- 不 probe / canary / live / paper
- 不读 wallet / keypair / signer / 私钥
- 不创建 signer
- 不发送 transaction / approve / mint / swap / bridge
- 不写 production positions
- 不覆盖 shadow 原始表
- 不接 paid RPC / paid indexer
- **不**覆盖 V2 FINAL_VERDICT
- **不**修改 data_dir

## 5. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_readonly_collector_6h_run/20260605_043726/FINAL_VERDICT.json` (V2 FINAL_VERDICT, FAIL)
- `data/lp_long_horizon/20260605_043726/` (6 ckpts × 7 文件 = 42 文件, dedup 聚合 row counts)

## 6. 允许 next_stage (5-stage allowed set)

- `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1` (本 stage 推荐, gate PASS)
- `LP_LONG_HORIZON_NODE_REPORT_FIX_REPEAT`
- `LP_LONG_HORIZON_COLLECTOR_6H_FIX_REPEAT` (gate FAIL 时)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`
- `STOP_LP_RESEARCH_NOW`
