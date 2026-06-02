# Phase 1 — 上一轮 overnight run 收尾

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- old_run_id: `20260601_185436`
- 本机环境（不需要 ssh）

## 停止前事实

| 维度 | 值 |
|---|---|
| runner_active | yes（PID 2982619） |
| 启动 | `2026-06-01 21:13:13` |
| ELAPSED | `39224` 秒（≈ 10h54m） |
| 配置 max-hours | `10`（即 36000 秒） |
| 超时 | **是**，+3224s |
| data/pool_fee_velocity.csv | 1 行（仅 header） |
| data/swap_logs_decoded.csv | 1 行（仅 header） |
| run.log 最后时间 | `2026-06-02T05:11:25Z`（约 1 小时前停止推进） |
| 最近 20 个 checkpoint | 全部 `partial:true, root_cause:rpc_error:RuntimeError` |
| 是否生产/canary/live/paper | **否** — runner 源码中没有 wallet/signer/keystore 符号；与 `lpbot-live` / `lpbot-shadow` systemd unit 无关 |

## 决策

允许停止：runner active + 超时 + data 空 + 仅 read-only。

## 停止动作（仅停 1 个具名 tmux session）

```bash
sudo -u deploy tmux kill-session -t lp_bsc_fee_velocity_overnight_20260601_185436
```

停止后验证：

```text
tmux_session_gone
tmux_pid_2982617_gone
bash_pid_2982618_gone
runner_pid_2982619_gone
tee_pid_2982620_gone
```

未触碰：tmux daemon、deploy 用户其它 session、root 的 work/work-lp session、任何 systemd 服务。

## 收尾

执行：

```bash
bash scripts/collect_bsc_fee_velocity_overnight_artifacts.sh --local-only --run-id 20260601_185436
# → WARNING: final exists but may be stale; checkpoint/state.json newer than final by 36340s
python3 scripts/finalize_bsc_fee_velocity_overnight_run_v1_readonly.py \
  --run-id 20260601_185436 \
  --report-dir reports/lp_bsc_fee_velocity_overnight/20260601_185436 \
  --mode auto
# → branch=partial, decision_reason=auto_runner_inactive_checkpoint_partial
```

写入：

- `reports/lp_bsc_fee_velocity_overnight/20260601_185436/PARTIAL_FINAL_VERDICT.json`

不覆盖：

- `reports/lp_bsc_fee_velocity_overnight/20260601_185436/final/FINAL_VERDICT.json`（仍是 21:05 占位 stale；finalizer 已硬规则禁止覆盖）

## 权威状态

| 字段 | 值 |
|---|---|
| selected_pool_count | 8 |
| completed_target_count | 34 |
| expected_target_count | 40 |
| progress_pct_at_stop | 85.0% |
| authoritative_status_source | `checkpoint_partial` |
| finalizer_branch | `partial` |
| recommended_next_stage（来自 finalizer） | `LP_BSC_PANCAKESWAP_V3_FEE_VELOCITY_OVERNIGHT_RESUME_OR_REPEAT` |
| 本轮（recovery pipeline）take | 不 resume 上次的 overnight；先用 Phase 2 RPC matrix 找可用 endpoint，再走 smoke + short backfill。 |

## 安全标记

```text
wallet_or_tx_touched         = false
production_disturbed         = false
edge_proven                  = no
tiny_canary_allowed          = no
can_run_probe_now            = false
```
