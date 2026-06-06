# Pre-Run Safety Check

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: pre_run_safety_check
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- checked_at_utc: `2026-06-06T13:19:00Z`

## 0. 总结

✅ **All 12 safety checks passed**. `decision: PROCEED_TO_LAUNCH`. 12h partial collector 可以安全启动.

## 1. 12 个 safety checks

| # | Check | Status | Detail |
|---|---|---|---|
| 1 | no_running_long_horizon_collector | ✅ pass | ps aux 无 run_lp_long_horizon_readonly_stage_once / lp_long_horizon_readonly_collector_v1 / tmux: server 进程 |
| 2 | no_canary_live_paper | ✅ pass | ps aux 无 canary / lpbot-live / live / paper 进程 |
| 3 | no_wallet_keypair_process | ✅ pass | ps aux 无 keypair / private_key / mnemonic 进程 |
| 4 | no_sendTransaction_process | ✅ pass | ps aux 无 sendTransaction / eth_sendRawTransaction / eth_sendTransaction 进程 |
| 5 | partial_universe_no_placeholder | ✅ pass | 53 池**不**含 `<smoke_pool_` 或 `PENDING_*_RPC_VALIDATION` marker. `placeholder_pool_count=0` |
| 6 | selected_pool_count_ge_45 | ✅ pass | **53** >= 45 ✓ |
| 7 | partial_universe_chains_solana_bsc | ✅ pass | chain_distribution: solana=49, bsc=4. observed=['solana','bsc'], missing=['base'] |
| 8 | data_dir_writable | ✅ pass | `data/lp_long_horizon/20260606_131323` created and writable |
| 9 | report_dir_writable | ✅ pass | `reports/lp_long_horizon_readonly_12h_run/20260606_131323` created and writable |
| 10 | partial_universe_path_exists | ✅ pass | partial_observable_real_pool_universe_for_12h.json exists |
| 11 | approval_record_exists | ✅ pass | MANUAL_APPROVAL_RECORDED.json has correct approval_phrase |
| 12 | run_config_exists | ✅ pass | twelve_hour_partial_run_config.json has duration=12, no auto advance |

**Result**: `all_checks_passed: true`. `decision: PROCEED_TO_LAUNCH`.

## 2. 安全保证 (继续维持)

- **不** 启动 24h / 48h / 72h / 7d
- **不** 启动并行 collector
- **不** 启用 cron / systemd / daemon
- **不** probe / canary / live / paper
- **不** 读 wallet / seed / keypair / signer
- **不** 发送 transaction / approve / mint / swap / bridge
- **不** 写真实 RPC key / private_key / mnemonic / seed
- **不** 修改 12h data_dir (84 文件, 0 修改)
- **不** 修改 6h data_dir (42 文件, 0 修改)
- **不** 修改 supervisor stage runner
- **不** 修改 collector

## 3. 12h 时间表 (启动后)

| 阶段 | 时间 (UTC) |
|---|---|
| **Stage G launch (Tmux)** | **2026-06-06 13:20:00** |
| Stage G healthcheck (2-3min 后) | 2026-06-06 13:23:00 |
| 第 1 checkpoint | 2026-06-06 14:20:00 |
| 第 12 checkpoint (完成) | 2026-06-07 01:20:00 |
| 失败 fallback deadline | 2026-06-07 02:20:00 |

## 4. 锁定字段 (启动后)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | **true** (启动后) |
| `auto_advance_to_24h` | `false` |
| `do_not_treat_as_full_universe` | `true` |

## 5. 下游

进入 Stage G (launch 12h partial collector via tmux).
