# Local Sync Final Verdict V2

- status: **`RUNNING`**
- stage: `LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1`
- run_id: `20260601_185436`
- environment: `vps_local`（不需要 ssh）
- supersedes: `LOCAL_SYNC_FINAL_VERDICT.json`

## 字段语义修正

| 维度 | v1 (`LOCAL_SYNC_FINAL_VERDICT.json`) | **v2（本文件）** |
|---|---|---|
| 文件已同步 vs 内容当前 | 单字段 `vps_final_synced=false` 混淆 | 拆 `vps_final_file_synced=true` + `vps_final_is_current=false` + `vps_final_is_stale=true` |
| selected_pool_count | 顶层写 `0`（来自 stale final） | 顶层写 `checkpoint_selected_pool_count=8` + `final_selected_pool_count_field=0` + `selected_pool_zero_from_stale_final=true` |
| root_cause | `unknown` | `stale_final_bootstrap_placeholder_not_current_run_state; data_csvs_empty_due_to_rpc_runtime_errors_on_public_fallback` |
| status | `WARN` | `RUNNING`（runner 仍 active） |
| recommended_next_stage | `LP_BSC_FEE_VELOCITY_OVERNIGHT_INPUT_ROOT_FIX_AND_SMOKE_V1` | `WAIT_FOR_OVERNIGHT_COMPLETION` |

## 当前事实

| 字段 | 值 |
|---|---|
| tmux_session_active | **true** |
| runner_process_active | **true** |
| runner_pid | `2982619` |
| runner_user | `deploy` |
| runner_started_local | `2026-06-01 21:13:13` |
| checkpoint_selected_pool_count | **8** |
| completed / expected | **34 / 40 (85.0%)** |
| pool_fee_velocity 行数 | 0（仅 header） |
| swap_logs_decoded 行数 | 0（仅 header） |
| partial checkpoint 占比 | 58.8% (20/34)，全部 `rpc_error:RuntimeError` |
| rpc_env_key | `public_fallback` |
| final_exists | true |
| final_mtime | 1780340745 (≈ 2026-06-01 21:05) |
| final_is_current | **false** |
| final_is_stale_or_unverified | **true** |
| authoritative_status_source | `checkpoint_and_run_log` |

## 根因

```text
1. final/FINAL_VERDICT.json 是 runner bootstrap 阶段（21:05，启动后 ~12 分钟）写入的占位文件；
   之后 10 小时的 scan loop 没有再回写 final。
2. data CSV 仍为 header-only，因为 public_fallback RPC 抛出 RuntimeError，
   34 个 checkpoint 中 20 个 partial。
3. checkpoint/state.json 与 run.log 才是当前权威状态来源。
4. runner 还在跑，--max-hours 10 已超出 wall-clock，但 next checkpoint 还未触发退出。
```

## 决策

```text
should_rerun_overnight                   = false
should_wait_or_finalize_current_run      = true
should_finalize_now                      = false   (runner 还活着)
data_usable_for_rebuild                  = false   (CSV 全是 header)
can_run_probe_now                        = false
edge_proven                              = no
tiny_canary_allowed                      = no
wallet_or_tx_touched                     = false
touched_trading_path                     = false
recommended_next_stage                   = WAIT_FOR_OVERNIGHT_COMPLETION
```

## 后续动作（按顺序）

1. **等 runner 自然退出**（`--max-hours 10` 已超时，预计本日内）。
2. runner 退出后再跑：
   ```bash
   bash scripts/collect_bsc_fee_velocity_overnight_artifacts.sh --local-only --run-id 20260601_185436
   python3 scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py \
       --run-id 20260601_185436 \
       --report-dir reports/lp_bsc_fee_velocity_overnight/20260601_185436 \
       --mode auto
   ```
3. 即便 completed_target_count = 40，只要 data CSV 仍为空（高度可能），
   finalizer 会自动降级到 `partial` 分支，写 `PARTIAL_FINAL_VERDICT.json`，
   `recommended_next_stage = LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT`。
4. **本轮不发起新 overnight，不 probe / canary / live / paper。**
