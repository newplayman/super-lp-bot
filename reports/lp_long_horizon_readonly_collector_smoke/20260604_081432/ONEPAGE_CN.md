# LP Long Horizon Read-only Collector Smoke — One-Pager

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- branch: `feat/supabase-postgres-deployment`
- status: **WARN** (smoke 100% 通过, 不开 long-run, 不开 probe / canary / live)

## 0. 一句话

smoke 模式跑通, 30 quote cells + 5 pool_snapshots + 25 fee_velocity + 5
liquidity_distribution + 7 market_regime + 1 actual_fee placeholder 全部生成,
6 类 schema 验证通过, 无 secret 泄漏, 无 production / shadow 写. 但 R0 long-run
readiness 0/9, `recommended_next_stage = LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT`
(补完 9 项 readiness 后再考虑 7D_RUN_REQUEST).

## 1. 核心字段

| 字段 | 值 | 含义 |
|---|---|---|
| `design_mode_ran` | `true` | design mode 跑通, exit 0 |
| `smoke_mode_ran` | `true` | smoke mode 1 pass 跑通, exit 0 |
| `selected_pool_count` | `5` | 5 protocol × 1 pool/协议 |
| `pool_snapshot_rows` | `5` | 5 pool_snapshots 写盘 |
| `quote_snapshot_rows` | `30` | 5 × 6 notional |
| `fee_velocity_rows` | `25` | 5 × 5 rolling windows |
| `liquidity_distribution_rows` | `5` | 5 pool |
| `market_regime_rows` | `7` | 7 regime 全部 placeholder |
| `schema_validation_pass` | `true` | 6/6 类 schema 全部通过 |
| `research_only_write_ok` | `true` | 写路径仅 `data/lp_long_horizon/...` |
| `long_run_ready` | `false` | 0/9 readiness (5 blocker) |
| `long_run_started` | `false` | 未启动 7d / 14d / 30d run |
| `can_run_probe_now` | `false` | locked |
| `tiny_canary_allowed` | `no` | locked |
| `edge_proven` | `no` | locked |
| `wallet_or_tx_touched` | `false` | locked |
| `transaction_sent` | `false` | locked |
| `recommended_next_stage` | `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT` | 补 9 项 readiness |

## 2. 阶段 A-I 总结

| 阶段 | 结果 |
|---|---|
| A workspace safety | PASS |
| B input evidence audit | PASS (8 input files; 10 locked; 13 prohibitions) |
| C collector CLI review | PASS (7 flags; 12 hard-rejected modes) |
| D design mode run | PASS (exit 0; 0 files written as expected) |
| E smoke mode run | PASS (exit 0; 7 files written; 24KB total) |
| F smoke output schema | PASS (6/6 schema; 0 secret; 0 production; 0 shadow) |
| G market regime sample | PASS (7/7 regimes; smoke_placeholder=true; no fabrication) |
| H collector health | PASS (smoke 100% OK; long-run spec complete 5/5; readiness 0/9) |
| I next stage decision | PASS (FIX_REPEAT chosen; 7 fix tasks) |
| J final verdict | PASS (this file) |

## 3. safety 12 字段全部 locked

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
  "smoke_placeholder_only": true,
  "secret_leak_count": 0,
  "production_write_count": 0,
  "shadow_overwrite_count": 0
}
```

## 4. smoke 输出 (research-only)

```
data/lp_long_horizon/20260604_081432/collector_smoke/
├── pool_snapshots.jsonl              5 records,  2490B
├── quote_snapshots.jsonl            30 records,  8778B
├── fee_velocity.jsonl               25 records,  7900B
├── liquidity_distribution.jsonl      5 records,  1383B
├── market_regime.jsonl               7 records,  1516B
├── actual_fee_accrual_placeholder.json  1 object,  729B
└── smoke_summary.json                1 object, 1461B
```

合计 72 条 jsonl record + 2 个 JSON object, 约 24KB. 全部 `smoke_placeholder=true`,
无真实 on-chain 数据.

## 5. long_run readiness 0/9 (待 FIX_REPEAT 补完)

- [ ] source_adapter_implemented (4 source: solana_rpc / coingecko / protocol_sdk / dex_screener)
- [ ] classifier_implemented (7 regime 函数)
- [ ] rate_limit_retry_backoff_implemented (per Stage D spec)
- [ ] abort_condition_implemented (5 conditions)
- [ ] sqlite_enabled (R0 long-run 数据量 100MB+)
- [ ] paid_rpc_indexer_integrated (Helius / Triton / Shyft)
- [ ] error_rate_monitor_implemented (prometheus / grafana)
- [ ] cron_systemd_configured (R0 long-run background)
- [ ] manual_approval_recorded (单独 approval stage)

## 6. 下一阶段: LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT

任务清单:
1. 实装 4 source adapter (替换 stub)
2. 实装 7 regime classifier
3. 接入 paid RPC / indexer
4. 实装 5 abort condition
5. manual approval 流程 (LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_APPROVAL_V1)
6. 回归 smoke 验证实装后仍安全
7. (可选) prometheus / grafana 接入

## 7. 警示

- 当前不开 live / canary / paper / probe
- 当前不接 wallet / signer / keypair
- 当前不发 transaction / approve / swap / add_liquidity / remove_liquidity / collect_fee
- 当前不写 production positions / shadow 原始表
- 当前 smoke 1 pass 即退, 不长期跑 daemon
- `internal/core/execution/hard-disable` 仍 active, 不释放
- 7D_RUN_REQUEST 需在 FIX_REPEAT 完成后才能发起
- 7D_RUN 启动前必须有 manual approval 记录
