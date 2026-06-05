# ARTIFACT_INDEX — V1 (20260604_134918) 全文件清单

- run_id: `20260604_134918`
- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- status: FAIL (V1 salvage)
- index_at_utc: `2026-06-05T04:37:30Z`

## 1. V1 报告目录 (本目录)

| 文件 | 类型 | 来源 | 备注 |
|---|---|---|---|
| `V1_FAILURE_SALVAGE_CN.md` | CN markdown | salvage | V1 失败回填说明 (本文档) |
| `V1_FAILURE_SALVAGE.json` | JSON | salvage | V1 失败回填 JSON |
| `FINAL_VERDICT.json` | JSON | salvage | V1 FAIL verdict (status=FAIL, recommended_next_stage=V2) |
| `ONEPAGE_CN.md` | CN markdown | salvage | V1 一页纸总结 |
| `ARTIFACT_INDEX.md` | markdown | salvage | 本文件 |
| `logs/supervisor.log` | log | V1 supervisor | 含 [6h end] FAIL line + NameError traceback |
| `logs/supervisor.stdout.log` | log | V1 supervisor | 同上, 1.06 KB 镜像 |
| `logs/heartbeat/` | dir (24 files) | V1 supervisor | heartbeat 0, 1_1..1_4, 2_1..2_4, 3_1..3_4, 4_1..4_4, 5_1..5_4 |
| `logs/checkpoint/` | dir | V1 supervisor | 空 (checkpoint 在 data/ 目录) |

## 2. V1 数据目录 (data/lp_long_horizon/20260604_134918/)

| Checkpoint | 时间戳 (UTC) | 文件数 | 文件 |
|---|---|---|---|
| `checkpoint_1_1401/` | 14:01:30Z | 7 | pool_snapshots.jsonl, quote_snapshots.jsonl, fee_velocity.jsonl, liquidity_distribution.jsonl, market_regime.jsonl, actual_fee_accrual_placeholder.json, smoke_summary.json |
| `checkpoint_2_1501/` | 15:01:31Z | 7 | (同上) |
| `checkpoint_3_1601/` | 16:01:32Z | 7 | (同上) |
| `checkpoint_4_1701/` | 17:01:35Z | 7 | (同上) |
| `checkpoint_5_1801/` | 18:01:36Z | 7 | (同上) |
| `checkpoint_6_1901/` | 19:01:37Z | 7 | (同上) |

**V1 数据: 6 × 7 = 42 文件, 全部保留, 未修改**.

## 3. V1 周边 artifacts (其他目录)

| 文件 | 目录 | 备注 |
|---|---|---|
| `V1_STATUS_SNAPSHOT_CN.md` + `.json` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | 启动时 V0 vs V1 状态报告 (decd140) |
| `V1_COMPLETION_AUDIT_CN.md` + `.json` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | 完成时 FAIL 审计 (57dcd9c) |
| `previous_6h_invalid_audit.json` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V0 invalid 审计 (V0 = 短模式) |
| `MANUAL_APPROVAL_RECORDED.json` + `_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 6h 审批 |
| `six_hour_real_wallclock_config.json` + `_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 6h 参数冻结 |
| `pre_run_safety_check.json` + `_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 启动前安全 |
| `tmux_start_healthcheck.json` + `_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 启动 smoke check |
| `STAGE_H_INTERIM_STATUS_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 中间状态 |
| `STAGE_I_J_LATE_RETURN_CN.md` | `reports/lp_long_horizon_readonly_collector_6h_fix/20260604_134918/` | V1 早回报 + 晚回报合并 |
| `tests/test_lp_long_horizon_readonly_collector_6h_real_wallclock_v1.py` | `tests/` | V1 pytest (31/31 PASS) |

## 4. V1 Git commits

| Commit | 备注 |
|---|---|
| `85cf235` | research: start real 6h long horizon readonly collector 20260604_134918 |
| `303fc7d` | research: add 6h real wallclock supervisor pytest suite 20260604_134918 |
| `f035813` | research: stage I+J late return (pytest 31/31 + git publish) 20260604_134918 |
| `decd140` | research: V1 status snapshot (V0 invalid + V1 in-flight real 6h, V2 deferred) |
| `57dcd9c` | research: V1 completion audit (FAIL, 300 min, no FINAL_VERDICT, supervisor bugs) |

## 5. V2 关联 artifacts (V2 启动后补)

V2 artifacts 待 V2 (`LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`) 启动后写入 `reports/lp_long_horizon_readonly_collector_6h_v2/${RUN_ID}/` 与 `reports/lp_long_horizon_readonly_collector_6h_run/${RUN_ID}/`.

## 6. 完整性

| 维度 | 状态 |
|---|---|
| V1 数据完整性 | ✅ 6/6 checkpoint 42 文件保留 |
| V1 报告完整性 (salvage 视角) | ✅ 5 份报告补写 (salvage) |
| V1 git history | ✅ 5 commits 已 push |
| V1 进程清理 | ✅ supervisor gone, tmux killed |
| V1 安全审计 | ✅ 100% 通过 |
| 进入 V2 决定 | ✅ 触发 (V1 FAIL + runtime < 330) |
