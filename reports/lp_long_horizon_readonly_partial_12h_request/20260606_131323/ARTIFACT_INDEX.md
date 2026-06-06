# ARTIFACT INDEX — Partial 12h Readonly Continuous Observation Request V1

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- status: **RUNNING** (12h partial collector 启动成功, 2-3min healthcheck 通过)
- launched_at_utc: `2026-06-06T13:24:00Z`
- expected_end_time_utc: `2026-06-07T01:24:45Z`

## 1. Output files (in `reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `INPUT_EVIDENCE_AUDIT_CN.md` | 输入证据审计 (CN) |
| 2 | `input_evidence_audit.json` | 输入证据审计 (JSON) |
| 3 | `PARTIAL_12H_SCOPE_FREEZE_CN.md` | Partial 12h scope freeze (CN) |
| 4 | `partial_12h_scope_freeze.json` | Partial 12h scope freeze (JSON) |
| 5 | `partial_observable_real_pool_universe_for_12h.csv` | Partial universe (CSV) — 53 pools |
| 6 | `partial_observable_real_pool_universe_for_12h.json` | Partial universe (JSON, collector-ready) |
| 7 | `PARTIAL_OBSERVABLE_REAL_POOL_UNIVERSE_CN.md` | Partial universe 报告 (CN) |
| 8 | `MANUAL_APPROVAL_RECORDED_CN.md` | 审批记录 (CN) |
| 9 | `MANUAL_APPROVAL_RECORDED.json` | 审批记录 (JSON, also copied to `reports/lp_long_horizon_readonly_continuous_12h_extension/20260606_131323/`) |
| 10 | `TWELVE_HOUR_PARTIAL_RUN_CONFIG_CN.md` | 12h partial run config (CN) |
| 11 | `twelve_hour_partial_run_config.json` | 12h partial run config (JSON) |
| 12 | `PRE_RUN_SAFETY_CHECK_CN.md` | Pre-run safety check (CN) |
| 13 | `pre_run_safety_check.json` | Pre-run safety check (JSON) |
| 14 | `TMUX_OR_NOHUP_START_HEALTHCHECK_CN.md` | Start healthcheck (CN) |
| 15 | `tmux_or_nohup_start_healthcheck.json` | Start healthcheck (JSON) |
| 16 | `FINAL_VERDICT.json` | Final verdict (status=RUNNING, 含 spec-required 完整字段) |
| 17 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 18 | `ARTIFACT_INDEX.md` | 本文件 |
| 19 | `build_partial_universe.py` | Partial universe build helper (read-only) |

## 2. 12h partial collector (running, in `data/lp_long_horizon/20260606_131323/`)

| File | 描述 |
|---|---|
| `checkpoint_1_1324/` | 第 1 checkpoint (5xx MB) — 53 pool snapshots, 318 quote, 265 fee, 53 liq, 7 regime, 1 actual_fee placeholder |
| `data/lp_long_horizon/20260606_131323/logs/supervisor.log` | Stage runner log |
| `data/lp_long_horizon/20260606_131323/logs/heartbeat/heartbeat_0.json` | Initial heartbeat |
| `data/lp_long_horizon/20260606_131323/logs/checkpoint/` | Per-checkpoint logs |

## 3. Process state

- **PID**: 3871101 (alive)
- **Launch method**: nohup (tmux server not accessible in this env)
- **cmd**: `bash scripts/run_lp_long_horizon_readonly_stage_once.sh 20260606_131323 12h 12 reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/partial_observable_real_pool_universe_for_12h.json`
- **Coverage scope**: `partial_solana_bsc_real_universe`
- **Expected end time**: 2026-06-07T01:24:45Z
- **Expected checkpoint count**: 12
- **Current checkpoint**: 1/12 (ok, 13:24:45Z)

## 4. 锁定字段 (5 项全 false/no + 5 additional)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `true` (启动后) |
| `auto_advance_to_24h` | `false` |
| `do_not_treat_as_full_universe` | `true` |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 5. 严禁 (启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不**修改 12h data_dir (新增 12h partial 池是设计内, **不** 改 v2 12h data)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector

## 6. 12h 后 Stage H finalize (auto by stage runner)

`recommended_next_stage` 仅允许 4 个值:
- `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT`
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1`
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

**不得** 自动启动 24h.

## 7. 4-stage allowed next stages (per FINAL_VERDICT spec)

- `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` (12h 完成后 review)
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (Base RPC fix)
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_PARTIAL_EXTENSION_REQUEST_V1` (24h extension 需 user approval)
- `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

## 8. 输入证据 (本轮**只**读)

- `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/FINAL_VERDICT.json` (prior stage)
- `reports/lp_long_horizon_rpc_reachability_adapter_smoke_fix/20260606_103807/integrated_observable_smoke_retry.json`
- `reports/lp_long_horizon_real_pool_universe_coverage_expand/20260606_091120/expanded_real_pool_universe_for_12h_retry.json` (current 72-pool universe)
- `scripts/lp_long_horizon_readonly_collector_v1.py` (collector, 801 lines)
- `scripts/run_lp_long_horizon_readonly_stage_once.sh` (stage runner, 518 lines; finalize fix already in)

## 9. 12h 时间表 (post-launch)

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| Stage G launch (nohup, pid 3871101) | 2026-06-06 13:24:00 | ✅ done |
| Checkpoint 1/12 (smoke) | 2026-06-06 13:24:45 | ✅ done |
| Checkpoint 2/12 | 2026-06-06 14:24:45 | pending |
| ... | ... | ... |
| Checkpoint 12/12 (完成) | 2026-06-07 01:24:45 | pending |
| 失败 fallback deadline | 2026-06-07 02:24:45 | pending |
| Stage H finalize (auto) | 2026-06-07 01:24:45 ~ 02:24:45 | pending |
