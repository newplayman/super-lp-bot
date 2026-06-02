# 同步状态

- run_id: `20260601_185436`
- local_report_dir: `reports/lp_bsc_fee_velocity_overnight/20260601_185436`
- remote_run_dir: `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436`
- sync_source: `vps`
- data_synced: `yes`
- checkpoint_synced: `yes`
- logs_synced: `yes`
- final_synced: `yes`
- final_is_current: `no`
- final_is_stale: `yes`

## 已同步文件

- `data/swap_logs_decoded.csv`
- `data/pool_fee_velocity.csv`
- `data/pool_fee_velocity_summary.json`
- `checkpoint/state.json`
- `checkpoint/hourly_*.json`
- `logs/run.log`
- `final/FINAL_VERDICT.json`
- `final/ARTIFACT_INDEX.md`
- `final/BSC_FEE_VELOCITY_OVERNIGHT_RESULTS_CN.md`
- `final/bsc_fee_velocity_overnight_results.csv`
- `final/bsc_fee_velocity_overnight_results.json`
- `final/BSC_FEE_VELOCITY_BLOCKER_DIAGNOSIS_CN.md`
- `final/bsc_fee_velocity_blocker_diagnosis.csv`
- `final/bsc_fee_velocity_blocker_diagnosis.json`
- `final/BSC_ECONOMICS_PREVIEW_WITH_OVERNIGHT_FEE_CN.md`
- `final/bsc_economics_preview_with_overnight_fee.csv`
- `final/bsc_economics_preview_with_overnight_fee.json`

## 观察

- VPS 当前 tmux 任务仍在运行。
- `checkpoint/state.json` 里 `selected_pool_count = 8`。
- `logs/run.log` 仍持续推进到 `2026-06-02T04:37:40Z` 之后的状态。
- `final/FINAL_VERDICT.json` 的时间戳早于当前 checkpoint / log，属于旧收口文件，不是当前权威最终结果。
