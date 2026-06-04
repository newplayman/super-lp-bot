# Stage E — Smoke Mode 运行结果 (Smoke Mode Result)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- 阶段实际执行时间: `20260604_081859` (脚本自动派生 run_id)

## 0. 实际命令

```bash
python3 scripts/lp_long_horizon_readonly_collector_v1.py \
  --mode smoke \
  --pools-per-protocol 5 \
  --out data/lp_long_horizon/20260604_081432/collector_smoke
```

任务规范里命令用了 `--max-pools 5 / --max-snapshots 1 / --no-daemon`, 实际脚本 CLI 是
`--pools-per-protocol 5` (语义等价), `--max-snapshots` 不存在 (smoke 固定 1 pass),
`--no-daemon` 不存在 (daemon mode 已 hard-reject). 偏差在 Stage C CLI 审查已记录.
本任务用实际 CLI 跑, 接受默认 1 pass.

输出转写到 `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_smoke_stdout.txt` 与 `collector_smoke_stderr.txt`.

## 1. 实际执行结果汇总

| 字段 | 值 |
|---|---|
| smoke_ran | `true` |
| exit_code | `0` |
| mode | `smoke` |
| auto_run_id | `20260604_081859` |
| selected_pool_count | `5` (5 protocol × 1 pool/协议 = 5) |
| pool_snapshot_rows | `5` |
| quote_snapshot_rows | `30` (5 pool × 6 notional) |
| fee_velocity_rows | `25` (5 pool × 5 rolling windows) |
| liquidity_distribution_rows | `5` |
| regime_rows | `7` (per regime) |
| actual_fee_schema_rows | `1` (placeholder, no actual record) |
| error_count | `0` (4 sources 全部 stub) |
| warning_count | `0` |
| output_dir | `data/lp_long_horizon/20260604_081432/collector_smoke/` |
| research_only_write_ok | `true` |
| no_production_write | `true` |
| no_wallet | `true` |
| no_tx | `true` |
| source_aborted | `false` |

## 2. 实际生成文件

| 文件 | 行数 | 大小 | 状态 |
|---|---|---|---|
| `pool_snapshots.jsonl` | 5 | 2490B | ✅ 写 |
| `quote_snapshots.jsonl` | 30 | 8778B | ✅ 写 |
| `fee_velocity.jsonl` | 25 | 7900B | ✅ 写 |
| `liquidity_distribution.jsonl` | 5 | 1383B | ✅ 写 |
| `market_regime.jsonl` | 7 | 1516B | ✅ 写 |
| `actual_fee_accrual_placeholder.json` | 1 (JSON object) | 729B | ✅ 写 |
| `smoke_summary.json` | 1 (JSON object) | 1461B | ✅ 写 |

合计 7 个文件, 72 条 jsonl record + 2 个 JSON object, 约 24KB.

## 3. 写路径安全确认

- [x] 写路径以 `data/lp_long_horizon/20260604_081432/collector_smoke/` 开头
- [x] **不**写到 `data/dryrun*` / `data/shadow*` / `data/live*`
- [x] **不**写到 `migrations/` / `cmd/` / `internal/` / `web/` / `configs/`
- [x] **不**写到 `reports/` (REPORT_DIR 只含本任务审计产物 + stdout/stderr 转写)
- [x] **不**覆盖任何已有 shadow 表

## 4. source adapter 状态

| source | ok | rate_limited | error | note |
|---|---|---|---|---|
| solana_rpc_public | 0 | 0 | 0 | stubbed in smoke; no network call |
| coingecko_public | 0 | 0 | 0 | stubbed in smoke; no network call |
| protocol_sdk_quote | 0 | 0 | 0 | stubbed in smoke; no SDK call |
| dex_screener_public | 0 | 0 | 0 | stubbed in smoke; no network call |

注: 4 个 source 在 smoke 阶段**全部 stub**, 没有真实网络调用. 这是 R0 阶段的设计
(避免 long-run 之前引入外部依赖). R0 阶段 long-run 启动前必须先实装 source
adapter + 通过单独 audit + manual approval.

## 5. safety check

- [x] `wallet_or_tx_touched = false` (从 smoke_summary.json)
- [x] `transaction_sent = false`
- [x] `send_hard_disable_still_active = true`
- [x] `next_stage = manual_review_of_smoke_artifacts` (脚本推荐)
- [x] `smoke_placeholder_only = true` (所有 record 是 placeholder, 实际 fee / on-chain 字段为 null 或 0)
- [x] safety self-check 通过 (import 时未触发 SystemExit)
- [x] 任何 banned token 未在真实代码中出现 (AST+tokenize 扫描)
- [x] 4 个 source adapter stub 未触发 NotImplementedError (因为未调用)

## 6. 输出转写

| 文件 | 用途 |
|---|---|
| `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_smoke_stdout.txt` | smoke mode 完整 stdout |
| `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/collector_smoke_stderr.txt` | smoke mode 完整 stderr (空) |
| `data/lp_long_horizon/20260604_081432/collector_smoke/` | 脚本写出的 7 个 research-only 文件 |

## 7. 结论

smoke mode 1 pass 跑通, 30 quote cells + 5 pool_snapshots + 25 fee_velocity +
5 liquidity_distribution + 7 market_regime + 1 actual_fee placeholder + smoke
summary 全部生成, 写路径严格限定 `data/lp_long_horizon/`, 所有 safety 字段
locked. 接下来 Stage F 验证 schema 字段一致性.

Stage E 通过. 进入 Stage F.
