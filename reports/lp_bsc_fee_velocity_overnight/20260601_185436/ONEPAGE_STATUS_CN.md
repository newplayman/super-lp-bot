# 单页状态 — `20260601_185436`

```text
stage                        = LP_BSC_FEE_VELOCITY_OVERNIGHT_VPS_LOCAL_FINALIZE_V1
environment                  = vps_local (no ssh required)
local_run_dir                = /tmp/lp_bsc_fee_velocity_overnight_20260601_185436
status                       = RUNNING

tmux_session_active          = yes  (owned by user 'deploy')
runner_process_active        = yes  (PID 2982619, started 2026-06-01 21:13:13)
runner_max_hours             = 10   (already exceeded wall-clock; exit imminent)

checkpoint_selected_pool_count = 8
checkpoint_pool_count          = 8
windows                        = [24h, 72h, 7d, 14d, 30d]
expected_target_count          = 40
completed_target_count         = 34
remaining_target_count         = 6
progress_pct                   = 85.0
pools_touched                  = 7 of 8 (untouched: 0x6805E0...USDT 1.0%)
in_progress                    = 0x1401ff...|30d
rpc_env_key                    = public_fallback
partial_checkpoint_share       = 58.8% (20/34, root_cause rpc_error:RuntimeError)

pool_fee_velocity rows         = 0 (header only)
swap_logs_decoded rows         = 0 (header only)
data_usable_for_rebuild        = no

final_exists                   = yes
final_mtime                    = 2026-06-01 21:05  (bootstrap placeholder)
final_is_current               = no
final_is_stale_or_unverified   = yes
authoritative_status_source    = checkpoint_and_run_log
final_overwritten_this_run     = no

edge_proven                    = no
tiny_canary_allowed            = no
can_run_probe_now              = no
wallet_or_tx_touched           = no
touched_trading_path           = no
touched_wallet_tx_bridge_live  = no

recommended_next_stage         = WAIT_FOR_OVERNIGHT_COMPLETION
```

## 下一步（在 runner 自然退出后）

```bash
bash scripts/collect_bsc_fee_velocity_overnight_artifacts.sh \
  --local-only --run-id 20260601_185436

python3 scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py \
  --run-id 20260601_185436 \
  --report-dir reports/lp_bsc_fee_velocity_overnight/20260601_185436 \
  --mode auto
```

预计 finalize 会落到 `partial` 分支（因为 data CSV 仍为空），输出
`PARTIAL_FINAL_VERDICT.json` 与 `recommended_next_stage =
LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT`。

## 严格禁区（再次确认）

```text
不发起新 overnight long-run
不 probe
不 canary
不 live
不 paper
不触碰 wallet / signer / keystore
不调用 eth_sendTransaction / eth_sendRawTransaction
不修改策略执行路径
不覆盖 final/FINAL_VERDICT.json（runner 仍 active）
不覆盖 shadow 表 / production positions
```
