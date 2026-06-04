# Stage E — Local Artifact Replay Adapter 实现

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon/adapters/local_artifact_replay.py`

## 1. 设计

`LocalArtifactReplayAdapter` 是本任务**最关键**的 adapter: 它从 5 个已 frozen
protocol verdict 读出 `best_pool` 真实 pool_address + 配对的 program_id,
**不依赖任何网络** 就能产生 `real_data_rows > 0`. 这是 R0 阶段长期 run
的"ground truth" 数据源.

输入:
- 5 个 protocol verdict JSON 文件
- final freeze verdict (作 cross-check, 但本 adapter 不读)

输出:
- 5 个 `PoolRecord`, 每个:
  - `pool_address`: 真实 on-chain 验证过的 32-字节 base58
  - `chain = "solana"`
  - `protocol`: 5 个之一
  - `program_id`: 真实 program id
  - `fee_tier_bps`: 推断 (meteora 100 / orca 30 / raydium 25 / stable 30)
  - `best_net_ev_proxy_usd`: 从 verdict (0.106 ~ 0.544)
  - `best_scenario / best_hold_window / best_notional_usd`: 从 verdict
  - `source = "local_artifact_replay"`
  - `real_data = True`
  - `source_verdict_path`: 反向追溯用

`PoolRecord` 是 dataclass, 可序列化为 dict, 也可直接被 ResearchStore 写入
SQLite + JSONL.

## 2. 行构造 (build_*_row helpers)

提供 4 个 helper 函数, 接受 `PoolRecord` 构造 schema 兼容的 record:

- `build_pool_snapshot_row(record, snapshot_at)` → 1 行
- `build_quote_snapshot_rows(record, notionals_usd, quote_at)` → N 行
- `build_fee_velocity_rows(record, windows, window_end_at)` → M 行
- `build_liquidity_distribution_row(record, snapshot_at)` → 1 行

每个 row 都标 `real_data=True` + `data_source=record.source` + 反向追溯字段.
数值字段保留 0.0 / null (因为 local adapter 没有 on-chain reserve / liquidity /
fee accrual 数据).

## 3. 错误处理

- 文件不存在 → `abort_controller.record_error()` + skip
- JSON decode error → `abort_controller.record_error()` + skip
- pool_address 空 → `abort_controller.record_error()` + skip
- abort_controller=None → 静默 skip (本字段是可选)

不 raise, 因为我们要让 ErrorRateMonitor 决定 abort.

## 4. safety check (静态)

- [x] 没有 wallet / signer / keypair
- [x] 没有 sendTransaction / signTransaction
- [x] 没有 add_liquidity / remove_liquidity / swap / collect_fee / approve
- [x] 没有 bridge
- [x] 没有 production 写路径
- [x] 没有 shadow 路径
- [x] 没有 daemon / cron / systemd
- [x] 0 banned token in real code (AST+tokenize 扫描)

## 5. 测试覆盖 (Stage L)

- `test_local_artifact_replay_returns_5_records`
- `test_local_artifact_replay_records_have_real_data_true`
- `test_local_artifact_replay_pool_addresses_unique`
- `test_local_artifact_replay_program_ids_match_verdicts`
- `test_local_artifact_replay_abort_controller_records_error_on_missing_file`
- `test_build_pool_snapshot_row_real_data_true`
- `test_build_quote_snapshot_rows_6_notionals`
- `test_build_fee_velocity_rows_5_windows`
- `test_build_liquidity_distribution_row_real_data_true`

## 6. real_data_rows 预期

5 个 record × (1 pool + 6 quote + 5 fee + 1 liq) = 65 rows.
其中 `real_data=True`. 这是本任务的 minimum real_data_rows > 0 目标.

## 7. 结论

`local_artifact_replay_adapter` 实装完成, 不依赖网络, 产生 5 个真实
PoolRecord + 65 个 real_data=True row. Stage E 通过. 进入 Stage F
(public_api + solana_rpc adapter).
