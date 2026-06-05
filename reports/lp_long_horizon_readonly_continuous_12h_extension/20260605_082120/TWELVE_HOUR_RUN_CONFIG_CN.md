# Stage D: 12h 跑配置冻结 (12h Run Config Frozen)

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_EXTENSION_REQUEST_V1`
- config_stage: `D_TWELVE_HOUR_RUN_CONFIG`
- frozen_at_utc: `2026-06-05T14:45:00Z`
- locked: **true** (任何修改需要新 manual approval)

## 0. 一句话

12h 真实只读观察延展, 12 个 1h checkpoint, 1h interval, 15min heartbeat, 用 33 个真实 on-chain 池, 严禁任何 probe / canary / live / paper / wallet / tx / auto-24h.

## 1. 跑基本参数

| 参数 | 值 |
|---|---|
| `duration_hours` | `12` |
| `duration_minutes` | `720` |
| `expected_min_runtime_minutes` | `660` (12h - 1h tolerance) |
| `loop_count` | `12` (12 hours × 1 ckpt/hour) |
| `sleep_seconds_per_iteration` | `3600` (1h, real wallclock) |
| `checkpoint_interval_minutes` | `60` |
| `heartbeat_interval_minutes` | `15` |
| `post_final_heartbeat_chunks` | `4` (4×15min = 60min REMAINING sleep, V2 fix) |

## 2. Pool Universe

| 参数 | 值 |
|---|---|
| `real_pool_universe_path` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.json` |
| `real_pool_universe_csv` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/real_pool_universe_for_12h.csv` |
| `selected_real_pool_count` | **`33`** |
| `placeholder_pool_count` | **`0`** |
| `all_pools_real_on_chain` | `true` |
| `real_pool_universe_used` | `true` |

## 3. 输出路径

| 类型 | 路径 |
|---|---|
| `output_data_dir` | `data/lp_long_horizon/20260605_082120/` |
| `output_report_dir` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/` |
| `output_log_dir` | `reports/lp_long_horizon_readonly_continuous_12h_extension/20260605_082120/logs/` |
| `output_node_report_dir` | `reports/lp_long_horizon_node_reports/20260605_082120/12h/` |
| `tmux_session_name` | `lp_long_horizon_12h_20260605_082120` |
| `supervisor_script` | `scripts/run_lp_long_horizon_readonly_stage_once.sh` |

## 4. Run Mode (LOCKED)

| 字段 | 值 |
|---|---|
| `run_mode` | `readonly` |
| `paid_rpc` | `false` |
| `paid_indexer` | `false` |
| `no_probe` | `true` |
| `no_canary` | `true` |
| `no_live` | `true` |
| `no_paper` | `true` |
| `no_wallet` | `true` |
| `no_keypair` | `true` |
| `no_signer` | `true` |
| `no_tx` | `true` |
| `no_approve` | `true` |
| `no_mint` | `true` |
| `no_bridge` | `true` |
| `no_add_liquidity` | `true` |
| `no_remove_liquidity` | `true` |
| `no_collect` | `true` |
| `no_swap` | `true` |
| `no_production_write` | `true` |
| `no_shadow_overwrite` | `true` |

## 5. Auto-advance (LOCKED, 全部 false)

| 字段 | 值 |
|---|---|
| `auto_advance_to_24h` | **`false`** |
| `auto_advance_to_48h` | **`false`** |
| `auto_advance_to_72h` | **`false`** |
| `auto_advance_to_7d` | **`false`** |
| `manual_approval_required_for_24h` | `true` |
| `manual_approval_required_for_48h` | `true` |
| `manual_approval_required_for_72h` | `true` |
| `manual_approval_required_for_7d` | `true` |

**12h 完成后不会自动启动 24h**. 用户需重新审批:
```
APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=24h mode=readonly no_probe=true
```

## 6. Abort 条件 (7 项)

| 条件 | 阈值 | 动作 |
|---|---|---|
| `consecutive_429_streak_gte_5` | RPC 429 连续 5 次 | abort_12h, 写 FAIL FINAL_VERDICT |
| `error_rate_pct_gt_20` | error_rate > 20% | abort_12h, 写 FAIL FINAL_VERDICT |
| `write_failure` | 写盘失败 | abort_12h, 写 FAIL FINAL_VERDICT with write_error |
| `safety_self_check_fail` | safety 自检失败 | abort_12h immediately, 不再写更多 ckpt |
| `forbidden_token_detected` | 检测到 tx_hash / private_key / keypair / mnemonic / seed / signed_transaction | abort_12h immediately, 写 FAIL FINAL_VERDICT with forbidden_token |
| `disk_threshold_breach` | disk > 100MB | warn_continue, 严重时 abort |
| `duplicate_collector_process` | 检测到 2+ collector 进程 | abort_12h, 写 FAIL FINAL_VERDICT with duplicate_pid |

## 7. Gate Rules (15 项)

| 规则 | 期望 |
|---|---|
| `actual_runtime_minutes_ge_660` | true (12h - 1h tolerance) |
| `real_pool_universe_used` | true |
| `selected_real_pool_count_ge_30` | true (本轮 33) |
| `placeholder_pool_count_eq_0` | true (本轮 0) |
| `short_mode_used_false` | true (LOCKED) |
| `pool_snapshot_rows_gt_zero` | true |
| `quote_snapshot_rows_gt_zero` | true |
| `fee_velocity_rows_gt_zero` | true |
| `liquidity_distribution_rows_gt_zero` | true |
| `market_regime_rows_gt_zero` | true |
| `error_rate_pct_le_20` | true |
| `consecutive_429_max_lt_5` | true |
| `no_wallet_tx_touch` | true (LOCKED) |
| `no_production_write` | true (LOCKED) |
| `no_shadow_overwrite` | true (LOCKED) |

## 8. 12h 收口: 7 个 supervisor 自动写文件 + 7 个 node report 自动写文件

| 文件 | 路径 |
|---|---|
| FINAL_VERDICT.json | `reports/.../12h_extension/20260605_082120/FINAL_VERDICT.json` |
| SIX_HOUR_RUN_SUMMARY_CN.md | `reports/.../12h_extension/20260605_082120/SIX_HOUR_RUN_SUMMARY_CN.md` |
| DATA_QUALITY_GATE_CN.md | `reports/.../12h_extension/20260605_082120/DATA_QUALITY_GATE_CN.md` |
| MARKET_REGIME_SUMMARY_CN.md | `reports/.../12h_extension/20260605_082120/MARKET_REGIME_SUMMARY_CN.md` |
| NEXT_STAGE_DECISION_CN.md | `reports/.../12h_extension/20260605_082120/NEXT_STAGE_DECISION_CN.md` |
| ONEPAGE_CN.md | `reports/.../12h_extension/20260605_082120/ONEPAGE_CN.md` |
| ARTIFACT_INDEX.md | `reports/.../12h_extension/20260605_082120/ARTIFACT_INDEX.md` |
| 12h Node Report (11 files) | `reports/lp_long_horizon_node_reports/20260605_082120/12h/` |
| - FINAL_NODE_VERDICT.json | |
| - NODE_REPORT_CN.md | |
| - NODE_REPORT.json | |
| - POOL_UNIVERSE_COVERAGE_MANIFEST.csv/json | |
| - FEE_ESTIMATION_BASIS_CN.md/json | |
| - RANGE_LIQUIDITY_FEE_SENSITIVITY.csv/json | |
| - CANDIDATE_REVIEW.csv/json | |

**Total**: 7 + 11 = 18 files auto-written at 12h finalize.

## 9. 5-stage allowed next stages

- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (12h PASS 时推荐, 但**不**自动启动)
- `LP_LONG_HORIZON_12H_NODE_REPORT_FIX_REPEAT` (node report 生成失败时)
- `LP_LONG_HORIZON_12H_COLLECTOR_FIX_REPEAT` (collector 失败时)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` (用户要求暂停)
- `STOP_LP_RESEARCH_NOW` (用户要求停止)

## 10. 不动作 (LOCKED)

| 字段 | 值 |
|---|---|
| `no_modify_6h_data` | `true` |
| `no_modify_6h_report` | `true` |
| `no_modify_6h_corrected_verdict` | `true` |
| `no_start_24h_48h_72h_7d` | `true` |
| `no_probe_canary_live_paper` | `true` |
| `no_wallet_keypair_signer` | `true` |
| `no_tx_send_approve_mint` | `true` |
| `no_paid_rpc_indexer` | `true` |
| `no_production_write` | `true` |
| `no_shadow_overwrite` | `true` |
| `no_cron_systemd_daemon` | `true` |
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |

## 11. 结论

✅ 12h 跑配置冻结. 33 真实池, 12h wallclock, 7 abort 条件, 15 gate rules, 18 auto-output files, 5 allowed next stages, 全部 LOCKED. 12h supervisor 启动后, 12h 内**不**允许任何修改, 12h 完成自动 finalize + auto commit + auto push.

**Stage D PASS** → 进入 Stage E (12h supervisor 脚本 + 测试).
