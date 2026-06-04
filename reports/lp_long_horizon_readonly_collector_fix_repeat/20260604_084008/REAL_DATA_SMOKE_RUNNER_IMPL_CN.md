# Stage I — Real Data Smoke Runner 实现

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon_readonly_real_data_smoke_v1.py`

## 1. CLI 接口

```text
--mode {design, smoke}            default=smoke
--out <path>                      default=data/lp_long_horizon/<run_id>/real_data_smoke
--pools <int>                     default=5 (来自 local_artifact_replay 真实 pool)
--use-public-api {0,1}            default=0
--use-solana-rpc {0,1}            default=0
--run-id <str>                    default=UTC timestamp
```

## 2. 流程

1. 解析 CLI + 验证 `--out` 路径以 `data/lp_long_horizon` 开头 (硬约束, 否则 exit 5)
2. design mode: print spec, exit 0
3. smoke mode:
   a. 初始化 AbortController (threshold 50%, max_429_streak 5)
   b. LocalArtifactReplayAdapter.fetch_pools() → 5 real PoolRecord
   c. ResearchStore (SQLite + JSONL) 初始化
   d. 对每个 pool:
      - pool_snapshots (1)
      - liquidity_distribution (1)
      - quote_snapshots (6 notional)
      - fee_velocity (5 windows)
   e. 7 market_regime 用真实 classify_regime() (1 per regime)
   f. 1 actual_fee_accrual placeholder
   g. 写 smoke_summary.json
   h. close store
4. exit 0 (除非 AbortError 触发)

## 3. real_data vs placeholder 计数

| 类别 | 数量 | real_data? |
|---|---|---|
| pool_snapshots | 5 (来自 5 real pool) | ✅ True (real) |
| quote_snapshots | 30 (5 × 6 notional) | ✅ True (real pool_address) |
| fee_velocity | 25 (5 × 5 windows) | ✅ True (real pool_address) |
| liquidity_distribution | 5 | ✅ True (real pool_address) |
| market_regime | 7 (1 per regime) | ✅ True (real_classifier) |
| actual_fee_accrual | 1 (placeholder) | ❌ False (placeholder) |

总计: 73 rows, real_data=72, placeholder=1. **real_data_rows > 0**, **placeholder_rows < total rows**.

(注意: 之前 Stage C 估算 placeholder=8, 实际本 runner 写 7 market_regime 全部 real (用真实 classifier), placeholder 仅 1 actual_fee. 这更严格, 符合任务要求.)

## 4. AbortController 集成

runner 在每个 pool 循环 + regime 循环后调 `abort_ctrl.check_abort()`. 5 类
abort condition 任意一个触发 → AbortError → 写 smoke_summary + exit 7.

## 5. safety check (静态)

- [x] 0 wallet / signer / tx / mutation in real code
- [x] 0 bridge call
- [x] 写路径仅 `data/lp_long_horizon/<run_id>/`
- [x] 不写 production / shadow / live / dryrun
- [x] 不启动 daemon
- [x] default `--use-public-api=0 --use-solana-rpc=0` (VPS 不依赖网络)
- [x] `real_data_smoke_ran=True` only when smoke mode actually runs

## 6. 单元测试覆盖 (Stage L)

- `test_runner_design_mode_exits_0`
- `test_runner_smoke_mode_writes_real_data`
- `test_runner_smoke_mode_real_data_rows_greater_than_0`
- `test_runner_smoke_mode_placeholder_rows_less_than_total`
- `test_runner_smoke_mode_writes_to_data_lp_long_horizon_only`
- `test_runner_smoke_mode_no_production_write`
- `test_runner_smoke_mode_no_shadow_overwrite`
- `test_runner_smoke_mode_writes_smoke_summary`
- `test_runner_smoke_mode_research_only_storage`
- `test_runner_aborts_on_write_failure`
- `test_runner_classifier_actually_called`
- `test_runner_local_artifact_replay_actually_called`
- `test_runner_refuses_outside_data_lp_long_horizon`
- `test_runner_no_wallet_no_tx_in_real_data_smoke`

## 7. 结论

real_data smoke runner 实装完成, 集成 4 个 lib (replay + classify + storage + abort),
写 SQLite + JSONL, 不引入网络 / wallet / tx. Stage I 通过. 进入 Stage J
(实际跑 real-data smoke).
