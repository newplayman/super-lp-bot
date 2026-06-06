# 12h Partial Run Config

- stage: `LP_LONG_HORIZON_READONLY_CONTINUOUS_12H_PARTIAL_REAL_UNIVERSE_REQUEST_V1`
- section: twelve_hour_partial_run_config
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- configured_at_utc: `2026-06-06T13:18:00Z`

## 0. 总结

✅ **12h partial run config 已就位**. 12h duration, 60min checkpoint, 15min heartbeat, 1h tolerance. coverage_scope=partial_solana_bsc_real_universe, full_coverage_ready=false, do_not_treat_as_full_universe=true. **不** 自动 advance 24h.

## 1. 关键字段

| 字段 | 值 |
|---|---|
| `duration_hours` | **12** |
| `checkpoint_interval_minutes` | **60** (1h per checkpoint) |
| `heartbeat_interval_minutes` | **15** (4 heartbeats per checkpoint) |
| `tolerance_min` | **60** (1h tolerance) |
| `expected_start_time_utc` | **`2026-06-06T13:20:00Z`** |
| `expected_end_time_utc` | **`2026-06-07T01:20:00Z`** (12h 后) |
| `expected_runtime_minutes` | **720** |
| `expected_checkpoint_count` | **12** |
| `expected_heartbeat_count_per_checkpoint` | **4** |
| `pool_universe_path` | `reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/partial_observable_real_pool_universe_for_12h.json` |
| `data_dir` | `data/lp_long_horizon/20260606_131323` |
| `report_dir` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323` |
| `log_dir` | `reports/lp_long_horizon_readonly_12h_run/20260606_131323/logs` |
| `session_name` | `lp_long_horizon_12h_partial_20260606_131323` |
| `coverage_scope` | `partial_solana_bsc_real_universe` |
| `full_coverage_ready` | **false** |
| `do_not_treat_as_full_universe` | **true** |
| `no_probe` | **true** |
| `no_wallet` | **true** |
| `no_tx` | **true** |
| `readonly` | **true** |
| `auto_advance_to_24h` | **false** |
| `auto_advance_to_next_stage` | **false** |
| `selected_pool_count` | **53** (49 Solana + 4 BSC V3) |
| `observable_chains` | `["solana", "bsc"]` |
| `missing_chains` | `["base"]` |
| `approved_stage` | **12h** |
| `approved_scope` | **partial_solana_bsc** |
| `approval_phrase` | `APPROVE_LP_LONG_HORIZON_READONLY_STAGE_RUN stage=12h mode=readonly no_probe=true scope=partial_solana_bsc` |
| `long_run_started` | **false** (启动时变 true) |

## 2. 启动参数 (Stage G 需用)

```bash
# Stage runner command (read-only mode, no probe, no auto-next)
tmux new-session -d -s lp_long_horizon_12h_partial_20260606_131323 \
  "POOL_UNIVERSE_PATH=reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/partial_observable_real_pool_universe_for_12h.json \
   bash scripts/run_lp_long_horizon_readonly_stage_once.sh 20260606_131323 12h 12 \
        reports/lp_long_horizon_readonly_partial_12h_request/20260606_131323/partial_observable_real_pool_universe_for_12h.json"
```

**关键参数**:
- `--pool-universe`: `partial_observable_real_pool_universe_for_12h.json` (Solana + BSC only)
- `--duration-hours`: 12
- `--readonly`: true
- `--no-probe`: true
- `--no-auto-next`: true (auto_advance_to_24h=false)

## 3. 12h 时间表

| 阶段 | 时间 (UTC) |
|---|---|
| Stage G launch (Tmux) | 2026-06-06 13:20:00 |
| Stage G healthcheck (2-3min 后) | 2026-06-06 13:23:00 |
| 第 1 checkpoint | 2026-06-06 14:20:00 |
| 第 2 checkpoint | 2026-06-06 15:20:00 |
| ... | ... |
| 第 12 checkpoint (完成) | 2026-06-07 01:20:00 |
| 失败 fallback deadline | 2026-06-07 02:20:00 (12h + 1h tolerance) |
| Stage H finalize (auto by stage runner) | 2026-06-07 01:20:00 ~ 02:20:00 |

## 4. 锁定字段 (5 项全 false/no + 7 additional)

| 字段 | 锁定值 |
|---|---|
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `long_run_started` | `false` (启动时变 true) |
| `auto_advance_to_24h` | `false` |
| `auto_advance_to_next_stage` | `false` |
| `do_not_treat_as_full_universe` | `true` |
| `no_collector_started` | `true` (启动时变 false) |
| `no_12h_retry_started` | `true` (启动时变 false) |
| `no_paid_rpc_key_committed` | `true` |
| `no_real_secret_committed` | `true` |

## 5. 严禁 (本轮全部不触发, 启动后仍不触发)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不启用 cron / systemd / daemon (仅 tmux session, no daemon mode)
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 写真实 RPC key / private_key / mnemonic / seed
- ❌ **不** 自动 advance 到 24h (auto_advance_to_24h=false)
- ❌ **不** 启动 12h retry 在 Base 链 (Base RPC 不可达)
- ❌ **不**修改 12h data_dir (84 文件, 0 修改)
- ❌ **不**修改 6h data_dir (42 文件, 0 修改)
- ❌ **不**修改 v2 12h FINAL_VERDICT / v2 6h FINAL_VERDICT / corrected verdicts / 12h node report
- ❌ **不**修改 supervisor stage runner
- ❌ **不**修改 collector

## 6. 下游

进入 Stage F (pre-run safety check) → G (launch 12h partial collector).
