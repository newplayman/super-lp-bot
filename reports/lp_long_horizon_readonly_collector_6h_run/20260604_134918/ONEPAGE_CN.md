# LP Long Horizon Read-only Collector 6h Real Wallclock Fix Repeat V1 — One-Pager (Salvage)

- run_id: `20260604_134918`
- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCKFIX_REPEAT_V1`
- status: **FAIL** (V1 salvage)
- salvage_at_utc: `2026-06-05T04:37:30Z`

## 一句话结论

V1 supervisor 跑 6 checkpoint 但因 bash loop 缺 1 次 sleep (5h 而非 6h) + Python `false` typo NameError 崩溃, gate FAIL (300.12 < 330), 推荐 V2.

## 关键字段

| 字段 | 值 |
|---|---|
| actual_runtime_minutes | 300.12 (期望 360) |
| gate_pass | false (300 < 330) |
| short_mode_used | false ✅ |
| checkpoints | 6/6 ✅ (42 文件) |
| FINAL_VERDICT | (salvage 补写) |
| data_quality_status | FAIL |
| can_advance_to_12h | false |
| can_run_probe_now | false |
| tiny_canary_allowed | "no" |
| auto_advance_started | false |
| wallet_or_tx_touched | false |
| transaction_sent | false |
| recommended_next_stage | `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2` |

## V1 失败根因

1. **bash loop 缺 1 次 sleep** (line 141 `if [ "$i" -lt $LOOP_COUNT ]`): 6 iterations 只有 5 sleeps = 5h wallclock.
2. **Python `false` typo** (line 222): lowercase `false` 在 Python heredoc 触发 NameError, finalize 崩溃.

## 数据完整性

- 6/6 checkpoints ✅ 42 文件 ✅ all real_data ✅ no fabrication ✅ no network ✅
- selected_pool_count: 5
- pool_snapshot_rows: 5 (deduped) / 30 (raw)
- quote_snapshot_rows: 180 (deduped) / 210 (raw)
- fee_velocity_rows: 150
- liquidity_distribution_rows: 30
- market_regime_rows: 42
- error_rate_pct: 0.0
- consecutive_429_max: 0

## 安全审计 (V1 全程 100% 通过)

- [x] no canary / live / paper
- [x] no wallet / keypair / signer
- [x] no sendTransaction
- [x] no production write
- [x] no shadow overwrite
- [x] no cron / systemd
- [x] no daemon leak
- [x] can_run_probe_now = false
- [x] tiny_canary_allowed = "no"
- [x] auto_advance_started = false

## V2 决策

V1 FAIL (gate false + finalize 失败 + runtime < 330) → **V2 触发**: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_REAL_WALLCLOCK_FIX_REPEAT_V2`.

V2 必须:
1. 修 supervisor bash loop: 改用 END_TS-based 控制 (START_TS + 21600)
2. 修 supervisor Python heredoc: false/true → False/True
3. 加 `set -euo pipefail`
4. finalize 失败也写 FAIL verdict
5. 加 V2 pytest 防止同类 bug

不得自动启动 12h. can_run_probe_now 保持 false. tiny_canary_allowed 保持 no.
