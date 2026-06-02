# Stopped stale read-only overnight run

- stage: `LP_BSC_FEE_VELOCITY_RECOVERY_AND_PROBE_PREFLIGHT_PIPELINE_V1`
- recovery_run_id: `20260602_060633`
- target_run_id: `20260601_185436`

## What was stopped

A single deploy-owned tmux session and its child python runner:

```text
tmux_session = lp_bsc_fee_velocity_overnight_20260601_185436   (uid 1000, deploy)
pid 2982617  tmux new-session -d -s lp_bsc_fee_velocity_overnight_20260601_185436 ...
pid 2982618    bash -c (the runner cmd)
pid 2982619      python3 scripts/lp_bsc_fee_velocity_overnight_runner.py --run-id 20260601_185436 --max-hours 10 ...
pid 2982620      tee /tmp/lp_bsc_fee_velocity_overnight_20260601_185436/logs/run.log
elapsed_at_stop  = 39224 seconds (10h54m)
configured_max   = 10 hours = 36000 seconds
overrun          = 3224 seconds
```

## Why safe to stop

1. The process is `lp_bsc_fee_velocity_overnight_runner.py`, a read-only script that does only `eth_call` and bounded `eth_getLogs`. The runner's own source contains no `eth_sendTransaction`, `eth_sendRawTransaction`, `signTransaction`, `Keystore`, or `from_private_key` calls. The matches for those strings in the runner source are dictionary keys in safety-self-reporting (e.g. `"eth_sendRawTransaction_called": False`), not actual invocations.
2. The runner is not a systemd service. It is not `lpbot-live`, `lpbot-shadow`, `lpbot-canary`, or `lpbot-paper`.
3. The runner overran its configured `--max-hours 10`. The host has no other matching runner. Re-checked `ps aux | egrep 'canary|lpbot-live|lpbot-paper|live|wallet|eth_send'` → no production processes were present.
4. The runner's data CSVs were header-only for the full 10h54m; the last 20 of 34 checkpoints reported `partial:true, root_cause:rpc_error:RuntimeError`. Keeping it alive only wastes the public_fallback RPC budget; it cannot recover the data.

## Why NOT a production process

- runner cwd: `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436` — not under `/opt/lpbot/lp-bot-v3*/bin/` (no compiled lpbot binary involved)
- runner cmdline: `python3 scripts/lp_bsc_fee_velocity_overnight_runner.py` — not `./bin/lpbot-live` / `./bin/lpbot-shadow` / `./bin/lpbot-canary`
- no shadow / live / canary / paper environment variables set on this PID (would have appeared in cmdline; verified absent)
- runner script name carries `_readonly`-equivalent contract; producing `BSC_OVERNIGHT_START_SAFETY_AUDIT_CN.md` with `wallet_or_tx_touched: no, tiny_canary_allowed: no, can_run_probe_now: no` at startup

## Method

```bash
sudo -u deploy tmux kill-session -t lp_bsc_fee_velocity_overnight_20260601_185436
```

Scope is strictly the single named session. `tmux ls` for the `deploy` user before and after confirms only this session disappeared; the user's other tmux daemon socket (`/tmp/tmux-1000/default`) and root's daemon (`/tmp/tmux-0/default`) are untouched. The four PIDs in the process tree (`2982617`, `2982618`, `2982619`, `2982620`) all exited together as expected when the tmux session was killed.

## Post-stop verification

```text
tmux_session_gone     ✓
tmux_pid_2982617_gone ✓
bash_pid_2982618_gone ✓
runner_pid_2982619_gone ✓
tee_pid_2982620_gone   ✓
no other lpbot-* processes touched
no shadow/live/canary processes were present at any point
```

## What was preserved

- `/tmp/lp_bsc_fee_velocity_overnight_20260601_185436/` — runner state, checkpoints, logs, data, scripts all retained for resume / forensics
- `reports/lp_bsc_fee_velocity_overnight/20260601_185436/final/FINAL_VERDICT.json` — NOT overwritten; remains the original bootstrap placeholder. The finalizer wrote `PARTIAL_FINAL_VERDICT.json` alongside.
