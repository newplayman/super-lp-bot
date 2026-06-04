# LP Long Horizon Read-only Collector Fix Repeat — Artifact Index

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`
- branch: `feat/supabase-postgres-deployment`

## 本阶段产物

| 文件 | 用途 |
|---|---|
| `STAGE_A_WORKSPACE_SAFETY_CN.md` | Stage A: workspace 安全检查 |
| `INPUT_EVIDENCE_AUDIT_CN.md` | Stage B: 8 input files + 5 real pool_address locked |
| `input_evidence_audit.json` | Stage B: 字段化 |
| `FIX_REPEAT_PLAN_CN.md` | Stage C: 6/9 readiness 目标 + 3 defer |
| `fix_repeat_plan.json` | Stage C: 字段化 |
| `RETRY_BACKOFF_UTILS_IMPL_CN.md` | Stage D: retry/backoff/abort 5 类条件 |
| `retry_backoff_utils_impl.json` | Stage D: 字段化 |
| `LOCAL_ARTIFACT_REPLAY_ADAPTER_IMPL_CN.md` | Stage E: 5 real PoolRecord 源 |
| `local_artifact_replay_adapter_impl.json` | Stage E: 字段化 |
| `PUBLIC_API_AND_SOLANA_RPC_ADAPTERS_IMPL_CN.md` | Stage F: opt-in adapter |
| `public_api_and_solana_rpc_adapters_impl.json` | Stage F: 字段化 |
| `REGIME_CLASSIFIER_IMPL_CN.md` | Stage G: 7 regime + 优先级 + decision tree |
| `regime_classifier_impl.json` | Stage G: 字段化 |
| `SQLITE_STORAGE_IMPL_CN.md` | Stage H: 6 DDL + 6 索引 + JSONL fallback |
| `sqlite_storage_impl.json` | Stage H: 字段化 |
| `REAL_DATA_SMOKE_RUNNER_IMPL_CN.md` | Stage I: 4 lib 编排 |
| `real_data_smoke_runner_impl.json` | Stage I: 字段化 |
| `REAL_DATA_SMOKE_RESULT_CN.md` | Stage J: 实际跑 72 real + 1 placeholder |
| `real_data_smoke_result.json` | Stage J: 字段化 |
| `FINAL_VERDICT.json` | Stage K: 本阶段 verdict |
| `ONEPAGE_CN.md` | Stage K: 一页纸总结 |
| `ARTIFACT_INDEX.md` | Stage K: 本索引 (本文件) |

## 新增文件 (本任务 commit 范围)

**14 个 lib / runner / test 文件**:
- `scripts/lp_long_horizon/__init__.py`
- `scripts/lp_long_horizon/utils/__init__.py`
- `scripts/lp_long_horizon/utils/retry.py`
- `scripts/lp_long_horizon/utils/abort.py`
- `scripts/lp_long_horizon/adapters/__init__.py`
- `scripts/lp_long_horizon/adapters/local_artifact_replay.py`
- `scripts/lp_long_horizon/adapters/public_api_coingecko.py`
- `scripts/lp_long_horizon/adapters/solana_rpc_readonly.py`
- `scripts/lp_long_horizon/classify/__init__.py`
- `scripts/lp_long_horizon/classify/market_regime.py`
- `scripts/lp_long_horizon/storage/__init__.py`
- `scripts/lp_long_horizon/storage/research_store.py`
- `scripts/lp_long_horizon_readonly_real_data_smoke_v1.py`
- `tests/test_lp_long_horizon_readonly_collector_fix_repeat_v1.py`

**research-only 输出 (不 commit, gitignore 之外但本任务不 add)**:
```
data/lp_long_horizon/20260604_085232/real_data_smoke/
├── pool_snapshots.jsonl              5 records / 4004B
├── quote_snapshots.jsonl            30 records / 10224B
├── fee_velocity.jsonl               25 records / 9105B
├── liquidity_distribution.jsonl      5 records / 1624B
├── market_regime.jsonl               7 records / 1699B
├── future_actual_fee_accrual.jsonl   1 record / 673B
├── research.sqlite                  73KB
└── smoke_summary.json                1217B
```

未修改:
- `scripts/lp_long_horizon_readonly_collector_v1.py` (上一阶段 smoke 脚本)
- `docs/LPBOT_RESEARCH_STATUS_CN.md` (本阶段是技术实施, 不是口径修正)
- `README.md`
- 任何 `cmd/` `internal/` `migrations/` `configs/` `web/` 文件
- 任何 `data/dryrun*` `data/shadow*` `data/live*` 表

## 上游依赖 (read-only, 本任务未改动)

- `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/` (12 份 smoke 产物)
- `reports/lp_research_final_freeze/20260604_051254/` (final freeze)
- `reports/lp_*_*/<RUN>/FINAL_VERDICT.json` (5 protocol verdicts, real pool_address source)

## 后续读取入口 (建议顺序)

1. `ONEPAGE_CN.md` (本任务一页纸)
2. `FINAL_VERDICT.json` (本任务 verdict)
3. `REAL_DATA_SMOKE_RESULT_CN.md` (实际跑结果)
4. `FIX_REPEAT_PLAN_CN.md` (实施计划)
5. `RETRY_BACKOFF_UTILS_IMPL_CN.md` (retry/backoff 设计)
6. `LOCAL_ARTIFACT_REPLAY_ADAPTER_IMPL_CN.md` (real_data 源)
7. `REGIME_CLASSIFIER_IMPL_CN.md` (7 regime 分类)
8. `SQLITE_STORAGE_IMPL_CN.md` (存储设计)
9. `reports/lp_long_horizon_readonly_collector_smoke/20260604_081432/ONEPAGE_CN.md` (上游 smoke)

## 后续阶段 (本任务不覆盖)

- `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_REQUEST_V1` (本任务 recommended_next_stage)
  - paid_rpc_indexer_integrated (Helius / Triton)
  - cron_systemd_configured
  - manual_approval_recorded
  - regression smoke
- `LP_LONG_HORIZON_READONLY_COLLECTOR_7D_RUN_V1` (manual approval 完成后, 实际跑 7d)
- 后续 R0 / R1 / R2 / R3 / R4 / R5 阶段
