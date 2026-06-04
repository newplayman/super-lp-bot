# Stage J — Real Data Smoke 运行结果 (Real Data Smoke Result)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`
- 实际执行时间: `20260604_085232`

## 0. 实际命令

```bash
# 1) design mode
python3 scripts/lp_long_horizon_readonly_real_data_smoke_v1.py --mode design
# exit 0

# 2) smoke mode (1 pass, real_data)
python3 scripts/lp_long_horizon_readonly_real_data_smoke_v1.py --mode smoke
# exit 0
```

## 1. 实际执行结果

| 字段 | 值 |
|---|---|
| real_data_smoke_ran | `true` |
| exit_code | `0` |
| selected_pool_count | `5` |
| real_data_rows | **`72`** |
| placeholder_rows | **`1`** |
| total_rows | `73` |
| sqlite_available | `true` |
| jsonl_only | `false` |
| sqlite_path | `data/lp_long_horizon/20260604_085232/real_data_smoke/research.sqlite` |
| sqlite_size | `73KB` |
| error_count | `0` |
| aborted | `false` |
| abort_reason | `None` |
| max_429_streak_hit | `false` |
| write_failures | `0` |
| safety_self_check_failures | `0` |
| banned_token_detected | `0` |
| wallet_or_tx_touched | `false` |
| transaction_sent | `false` |
| send_hard_disable_still_active | `true` |
| no_long_running_daemon | `true` |
| no_paid_rpc_called | `true` (use_public_api=0 + use_solana_rpc=0) |

## 2. SQLite 实际 row count (与 JSONL 一致)

| 表 | total | real_data | placeholder |
|---|---|---|---|
| pool_snapshots | 5 | 5 | 0 |
| quote_snapshots | 30 | 30 | 0 |
| fee_velocity | 25 | 25 | 0 |
| liquidity_distribution | 5 | 5 | 0 |
| market_regime | 7 | 7 | 0 |
| future_actual_fee_accrual | 1 | 0 | 1 |
| **total** | **73** | **72** | **1** |

## 3. 真实数据样本 (meteora_dlmm pool_snapshot)

```json
{
  "pool_address": "CnK82s8exdsK9nwqQ55kd9wcxoA22NwTchZJCBdu8LDa",
  "chain": "solana",
  "protocol": "meteora_dlmm",
  "program_id": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
  "fee_tier_bps": 100,
  "real_data": true,
  "data_source": "local_artifact_replay",
  "source_verdict_path": "reports/lp_meteora_dlmm_targeted_top_pool_feed/20260604_021913/FINAL_VERDICT.json",
  "best_net_ev_proxy_usd": 0.544,
  "best_scenario": "zero_il_lvr",
  "best_hold_window": "7d",
  "best_notional_usd": 2000,
  "snapshot_at": "2026-06-04T08:52:32Z"
}
```

- `pool_address` 是真实 on-chain 验证过的 32 字节 base58
- `program_id` 是 Meteora DLMM V8 program id
- `best_net_ev_proxy_usd=0.544` 来自 final freeze verdict
- `real_data=true` 标记

## 4. 真实 regime 分类 (market_regime)

第 1 条: `low_volatility_stable` (vol_7d=0.5 < 1, classifier 优先级 1)
其它 6 条 (priority 2-7 + 其它) 也都用真实 classify_regime 函数输出, 全部 `real_data=true`.

## 5. placeholder 唯一来源

`future_actual_fee_accrual.jsonl` 中 1 条, `real_data=false`, 标记
`r0_phase_status=schema only, no records; r1 requires user-provided tokenId`.
这是 spec 要求的"actual fee 需 R1 阶段 user 提供 tokenId 才填" 的 placeholder.

## 6. 验证项

- [x] `real_data_rows > 0` (= 72) ✅
- [x] `placeholder_rows < total` (= 1 < 73) ✅
- [x] `schema_validation_pass = true` (6 表字段对齐 schema) ✅
- [x] `research_only_write_ok = true` (写路径仅 `data/lp_long_horizon/...`) ✅
- [x] `can_run_probe_now = false` (locked) ✅
- [x] `tiny_canary_allowed = no` (locked) ✅
- [x] `wallet_or_tx_touched = false` ✅
- [x] `transaction_sent = false` ✅
- [x] abort_summary.aborted = false ✅
- [x] 5 类 abort condition 全部 0 触发 ✅

## 7. 写路径

```
data/lp_long_horizon/20260604_085232/real_data_smoke/
├── pool_snapshots.jsonl              5 records / 4004B
├── quote_snapshots.jsonl            30 records / 10224B
├── fee_velocity.jsonl               25 records / 9105B
├── liquidity_distribution.jsonl      5 records / 1624B
├── market_regime.jsonl               7 records / 1699B
├── future_actual_fee_accrual.jsonl   1 record / 673B
├── research.sqlite                  73KB (73 rows)
└── smoke_summary.json                1217B
```

合计 6 jsonl + 1 sqlite + 1 summary, 总 ~100KB.

## 8. 结论

real_data smoke 跑通, real_data_rows=72 > 0, placeholder_rows=1 < 73,
SQLite + JSONL 双写 OK, 0 error, 0 abort, exit 0. Stage J 通过. 进入
Stage K (Final verdict + docs).
