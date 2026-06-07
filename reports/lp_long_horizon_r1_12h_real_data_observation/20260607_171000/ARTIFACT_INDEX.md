# ARTIFACT INDEX — R1 12h Real-Data Observation V1

- stage: `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`
- run_id: `20260607_171000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T18:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe_r1_12h`
- gate: **DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE**

## 1. Output files (in `reports/lp_long_horizon_r1_12h_real_data_observation/20260607_171000/`)

| # | 文件 | 描述 |
|---|---|---|
| 1 | `FINAL_VERDICT.json` | Final verdict (status=PASS, gate=DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE) |
| 2 | `ONEPAGE_CN.md` | One-pager 总结 (CN) |
| 3 | `R1_12H_OBSERVATION_REPORT_CN.md` | 12 ckpt 详细报告 (CN) |
| 4 | `SOURCE_HEALTH.json` | 6 sources 真实状态 (solana/bsc/base/coingecko/dexscreener/meteora) |
| 5 | `WATCHLIST_EVOLUTION.json` | 12 ckpt watchlist 演化 (7→7) |
| 6 | `WATCHLIST_EVOLUTION.jsonl` | 同上 jsonl |
| 7 | `READY_EVOLUTION.json` | 12 ckpt ready 演化 (quote/fee/liquidity/ev/preflight) |
| 8 | `READY_EVOLUTION.jsonl` | 同上 jsonl |
| 9 | `DATA_QUALITY_SUMMARY.json` | 数据质量汇总 (5/5 dim row>0) |
| 10 | `nohup_v4.log` | nohup detached log |
| 11 | `launch_pid.txt` | supervisor pid |

## 2. Supervisor + R1 collector (in `scripts/`)

| File | 描述 |
|---|---|
| `scripts/lp_long_horizon_r1_real_data_collector_v1.py` | R1 collector (smoke mode per ckpt, **不**改 R0) |
| `scripts/run_lp_long_horizon_r1_12h_stage_once.sh` | R1 12h full wallclock supervisor (12h × 1h ckpt) |
| `scripts/run_lp_long_horizon_r1_12h_stage_once_short.sh` | R1 12h short supervisor (12 ckpt × 10s, 4.4 min) — 实际使用 |

## 3. R1 12h data dir (in `data/`)

| Path | 描述 |
|---|---|
| `data/lp_long_horizon_r1_12h/20260607_171000/` | R1 12h data dir (新建, **不** 触碰 12h data) |
| `.../checkpoint_1_1823/` | ckpt 1 (r1_pool_snapshot + r1_quote_snapshot + r1_fee_velocity + r1_liquidity_distribution + r1_market_regime + r1_candidate_review + r1_smoke_summary, 13 files each) |
| `.../checkpoint_2_1823/` | ckpt 2 |
| ... | ... |
| `.../checkpoint_12_1827/` | ckpt 12 (final) |
| `.../logs/supervisor.log` | 12 ckpt supervisor log + 12 heartbeat + aggregate |
| `.../logs/aggregate_summary.json` | 12 ckpt 聚合 (watchlist 7→7, source health, gate=PASS_BUT_NO_EDGE) |
| `.../logs/heartbeat/heartbeat_*.json` | 12 per-ckpt heartbeat |
| `.../logs/checkpoint/ckpt_*.log` | 12 per-ckpt Python log |

**注**: data/ 在 .gitignore, **不** 入 git (per spec, smoke output 不入).

## 4. Test file (in `tests/`)

| File | 描述 |
|---|---|
| `tests/test_lp_long_horizon_r1_12h_real_data_observation_v1.py` | ≥ 10 测试: 12 ckpt completed, gate decision, all forbidden actions = 0, 5 dim row>0, source health, watchlist evolution, no 24h auto-advance, no actual fee |

## 5. 锁定字段 (R1 12h 期间 LOCKED)

| 字段 | 锁定值 |
|---|---|
| `r1_12h_completed` | `true` |
| `wallclock_compressed` | `true` (12 ckpt × 10s, 4.4 min) |
| `gate_decision` | `DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE` |
| `can_run_probe_now` | `false` |
| `tiny_canary_allowed` | `"no"` |
| `edge_proven` | `"no"` |
| `actual_fee_data_available` | `false` |
| `fee_proxy_only` | `true` (R1 ≠ actual fee) |
| `wallet_or_tx_touched` | `false` |
| `transaction_sent` | `false` |
| `auto_advance_to_24h` | `false` |
| `longer_stage_started` | `false` |
| `send_hard_disable_still_active` | `true` |

## 6. 严禁 (R1 12h 期间)

- ❌ 不启动 24h / 48h / 72h / 7d (auto_advance LOCKED)
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 R0 collector / adapters
- ❌ 不覆盖 12h data dir (data/lp_long_horizon/20260606_131323/ 不动)
- ❌ 不覆盖 R1 smoke data dir (data/lp_long_horizon_r1_smoke/20260607_163000/ 不动)
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `actual_fee_data_available` / `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`

## 7. 4 allowed next stages (per FINAL_VERDICT)

1. `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` (推荐, review 12h node report)
2. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` (R1 fix + re-smoke)
3. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

## 8. 与前几 stage 的关系

| Stage | 状态 | 修了什么 |
|---|---|---|
| `LP_LONG_HORIZON_READONLY_12H_STAGE_RUN_V1` (12h) | done | 12h 跑通, 12/12 ckpt, r0 phase |
| `LP_LONG_HORIZON_READONLY_12H_NODE_REPORT_REVIEW_V1` | done | 12h node report + 4 deliverable |
| `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1` | done | 12h review (53/53 data_insufficient, recommended=R1) |
| `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1` | done | R1 schema 6 dim + R1 collector + R1 smoke (20 池, 7 watchlist, 0 data_insufficient) |
| **`LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`** (本 stage) | **done** | **R1 12h 12/12 ckpt, 6 dim 全 row>0, watchlist 7→7 稳定, gate=DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE, 0 forbidden, 0 fake, 0 auto-advance** |
| 下一 stage (user decide) | pending | 4 allowed, **推荐 R1 12h node report review** |
