# LP Long Horizon Read-only Collector Fix Repeat — One-Pager

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (6/9 readiness 完成, real_data smoke 通过, 仍不开 7d/14d/30d)

## 0. 一句话

不跑 7d / 不启动 daemon / 不接 wallet / 不发 tx. 补完 9 项 readiness 中
的 6 项 (source adapter + classifier + retry/backoff + abort + sqlite + error
rate monitor), 实跑 1 pass real_data smoke 产 72 real_data rows + 1 placeholder,
exit 0, 0 abort, 0 error. 留 3 项给 `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1`.

## 1. 核心字段 (per FINAL_VERDICT.json)

| 字段 | 值 | 含义 |
|---|---|---|
| `source_adapter_implemented` | `true` | 3 adapter (local_replay + public_api + solana_rpc) |
| `classifier_implemented` | `true` | 7 regime + 优先级 + decision tree |
| `retry_backoff_implemented` | `true` | retry_with_backoff + classify_429 + with_timeout |
| `abort_condition_implemented` | `true` | 5 类 abort condition (consecutive_429 / error_rate / write_failure / safety_self_check / banned_token) |
| `sqlite_enabled` | `true` | 6 表 + 6 索引 + JSONL fallback |
| `jsonl_storage_ready` | `true` | 6 jsonl 文件 + graceful fallback |
| `error_rate_monitor_implemented` | `true` | ErrorRateMonitor (threshold 50%, window 20) |
| `real_data_smoke_ran` | `true` | 1 pass 实际跑了 |
| `real_data_rows` | `72` | > 0 满足 |
| `placeholder_rows` | `1` | < total 73 满足 |
| `schema_validation_pass` | `true` | 6/6 表字段对齐 R0 schema |
| `research_only_write_ok` | `true` | 写路径仅 `data/lp_long_horizon/...` |
| `long_run_ready` | `false` | 6/9 (3 留给 7D_RUN) |
| `can_run_probe_now` | `false` | locked |
| `tiny_canary_allowed` | `no` | locked |
| `edge_proven` | `no` | locked |
| `wallet_or_tx_touched` | `false` | locked |
| `transaction_sent` | `false` | locked |
| `recommended_next_stage` | `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` | 下一步 |

## 2. 阶段 A-K 总结

| 阶段 | 结果 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (5 real pool_address 锁定) |
| C fix_repeat plan | PASS (target 6/9) |
| D retry/backoff/abort utils | PASS (5 类 abort condition) |
| E local_artifact_replay_adapter | PASS (5 real PoolRecord) |
| F public_api + solana_rpc adapters | PASS (opt-in) |
| G regime classifier | PASS (7 regime + 15+ test) |
| H sqlite storage | PASS (6 DDL + 6 index + JSONL fallback) |
| I real_data smoke runner | PASS (design + smoke, 7 regime inputs) |
| J real_data smoke run | PASS (72 real + 1 placeholder + 0 error) |
| K final verdict | PASS (this file) |

## 3. real_data smoke 输出

```
data/lp_long_horizon/20260604_085232/real_data_smoke/
├── pool_snapshots.jsonl              5 records / 4004B    (5 real, 0 placeholder)
├── quote_snapshots.jsonl            30 records / 10224B  (30 real, 0 placeholder)
├── fee_velocity.jsonl               25 records / 9105B    (25 real, 0 placeholder)
├── liquidity_distribution.jsonl      5 records / 1624B    (5 real, 0 placeholder)
├── market_regime.jsonl               7 records / 1699B    (7 real, 0 placeholder)
├── future_actual_fee_accrual.jsonl   1 record / 673B      (0 real, 1 placeholder)
├── research.sqlite                  73KB (73 rows: 72 real + 1 placeholder)
└── smoke_summary.json                1217B
```

合计: 73 rows, real_data=72, placeholder=1. **real_data_rows > 0** ✅, **placeholder_rows < total** ✅.

## 4. 9 项 readiness 当前状态

| 字段 | 状态 | 来源 |
|---|---|---|
| `source_adapter_implemented` | ✅ | 3 adapter (Stage E + F) |
| `classifier_implemented` | ✅ | 7 regime (Stage G) |
| `rate_limit_retry_backoff_implemented` | ✅ | retry + backoff + 429 + timeout (Stage D) |
| `abort_condition_implemented` | ✅ | 5 类 abort (Stage D) |
| `sqlite_enabled` | ✅ | 6 表 DDL + 6 索引 (Stage H) |
| `error_rate_monitor_implemented` | ✅ | ErrorRateMonitor (Stage D) |
| `paid_rpc_indexer_integrated` | ❌ | 留待 7D_RUN |
| `cron_systemd_configured` | ❌ | 留待 7D_RUN |
| `manual_approval_recorded` | ❌ | 留待 7D_RUN |

`long_run_ready` = `false` (6/9 完成, 仍需 7D_RUN_REQUEST_V1 + 3 项实装 + manual approval)

## 5. safety 17 字段

```json
{
  "touched_trading_path": false,
  "touched_wallet_tx_bridge_live_paper": false,
  "wallet_or_tx_touched": false,
  "solana_wallet_or_keypair_touched": false,
  "transaction_sent": false,
  "send_hard_disable_still_active": true,
  "no_paid_rpc_integration": true,
  "no_paid_indexer_integration": true,
  "no_protocol_re_run": true,
  "no_heuristic_modification": true,
  "no_long_running_daemon": true,
  "no_signer_creation": true,
  "no_7d_14d_30d_run": true,
  "secret_leak_count": 0,
  "production_write_count": 0,
  "shadow_overwrite_count": 0
}
```

## 6. 下一阶段: LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1

补 3 项 readiness:
1. paid_rpc_indexer_integrated (Helius / Triton / Shyft)
2. cron_systemd_configured (R0 长期 run 必须 background)
3. manual_approval_recorded (单独 stage 文档 + manual signature)

补完后再走 1 次 regression smoke, 然后进入 LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_V1.

## 7. 警示

- 当前不开 live / canary / paper / probe
- 当前不接 wallet / signer / keypair
- 当前不发 transaction / approve / swap / add_liquidity / remove_liquidity / collect_fee
- 当前不写 production positions / shadow 原始表
- 当前 real_data smoke 1 pass 即退, 不长期跑 daemon
- 任何 7D_RUN 启动前必须有 manual approval 记录
- `internal/core/execution/hard-disable` 仍 active, 不释放
