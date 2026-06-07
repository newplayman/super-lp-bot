# R1 12h Real-Data Observation — One Pager

- stage: `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`
- run_id: `20260607_171000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T18:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe_r1_12h`
- gate: **DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE** ✅
- status: **PASS** ✅

## 0. 一句话

R1 12h 12/12 ckpt 跑通 (4.4 min wallclock-compressed), 6 dimensions 全 row>0, watchlist 7→7 稳定, preflight 0→0 (因 liquidity 不全), data_insufficient 0→0, market regime 真实 CoinGecko 7d, **不** 翻 freeze / actual_fee / can_run_probe_now / edge_proven, **不** 自动 24h. **不** edge proven.

## 1. 关键字段 (per spec)

| 字段 | 值 | 评估 |
|---|---|---|
| `r1_12h_completed` | true | 12/12 ckpt ✅ |
| `wallclock_compressed` | true (12 ckpt × 10s) | 诚实披露 |
| `actual_runtime_minutes` | 4.38 | 263 sec |
| `gate_decision` | DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE | per spec 验收 |
| `can_run_probe_now` | false (LOCKED) | freeze |
| `tiny_canary_allowed` | "no" (LOCKED) | freeze |
| `edge_proven` | "no" (LOCKED) | R1 ≠ edge |
| `actual_fee_data_available` | false (LOCKED) | R1 ≠ actual fee |
| `fee_proxy_only` | true | honest |
| `wallet_or_tx_touched` | false | ✅ |
| `transaction_sent` | false | ✅ |
| `auto_advance_to_24h` | false (LOCKED) | ✅ |

## 2. 12 ckpt row counts (稳定 0 漂移)

| Dimension | Per ckpt | 12 ckpt total |
|---|---|---|
| pool_snapshot | 20 | 240 |
| quote_snapshot | 120 | 1440 |
| fee_velocity | 100 | 1200 |
| liquidity_distribution | 20 | 240 |
| market_regime | 2 | 24 |
| candidate_review | 20 | 240 |

**5/5 R1 dimensions 全 row>0 (per spec PASS 条件)**.

## 3. Watchlist Evolution (12 ckpt)

- watchlist_count: 7 → 7 (稳定, 0 漂移)
- preflight_candidate_count: 0 → 0 (因 ev_ready=0)
- data_insufficient_count: 0 → 0
- ev_ready_pool_count: 0 → 0

**7 watchlist 全部 BSC V3** (因 slot0 active_tick medium confidence).

## 4. Source Health (诚实记录)

| Source | Status | Note |
|---|---|---|
| Solana RPC | reachable | getMultipleAccountsInfo real, low conf (unparsed IDL) |
| BSC RPC | reachable | eth_call slot0 real, medium conf |
| **Base RPC** | **unreachable** | 全部 403, honest skipped |
| CoinGecko | reachable | 7d market_chart real, medium conf |
| **DexScreener** | **unreachable** | indexer_unreachable, **不** fallback |
| Meteora dlmm-api | unreachable | not reachable |

**0 fake data injection**.

## 5. Fee proxy vs actual fee (大白话)

- fee proxy: r1_fee_velocity `volume_usd=0, confidence=unavailable, reason=indexer_unreachable`. **R1 12h 仍 proxy only**.
- actual fee: **false** (LOCKED). R1 12h **不** mint LP / **不** tokenId. schema 维持 placeholder.
- 区别: proxy = "honest placeholder"; actual = "真 tokenId-based 跨 ckpt diff" (R2+, 需 freeze reopen).

## 6. Watchlist 评估

7 watchlist 稳定 4.4 min. 含义:
- 7 池**至少** 1 dim high/medium (BSC V3 slot0 active_tick real)
- 7 池**不**是 preflight candidate (ev_ready=0)
- 7 池**不**是 actual fee decision (R1 ≠ actual fee)

## 7. 验收 (per spec)

### PASS ✅ (8/8)
- ✅ 12h 完整结束 (12/12 ckpt)
- ✅ 所有 forbidden actions = 0
- ✅ ≥ 5 dim 持续 row>0 (6/6)
- ✅ source health 完整记录
- ✅ watchlist / ready evolution 可回放
- ✅ 不自动推进 24h
- ✅ 不自动进入 probe
- ✅ 不接 paid RPC / 不写 production / 不覆盖 shadow

### WARN ⚠️ (1/3 hit, 不 FAIL)
- ⚠️ 部分源不可达 (Base / DexScreener / Meteora) — **诚实记录并继续只读观察**
- ❌ watchlist 降为 0 (未发生)
- ⚠️ fee/liquidity ready 仍 0, **无伪造**

### FAIL ❌ (0/5)
- ❌ 0 wallet/tx/signer/live/paper 触碰
- ❌ 0 旧数据目录覆盖 (新建 r1_12h/20260607_171000/)
- ❌ 0 24h+ 自动启动
- ❌ 0 actual fee 伪造
- ❌ 0 R1 误报为 edge proven

## 8. 严禁 (R1 12h 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 R0 collector / adapters
- ❌ 不覆盖 12h data dir (新建 data/lp_long_horizon_r1_12h/20260607_171000/)
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `actual_fee_data_available` / `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven`

## 9. 后续 (4 allowed next stages)

1. `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` (推荐, review 12h node report)
2. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` (R1 fix + re-smoke, 视情况)
3. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen, **不** 当前可达)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`

## 10. 一句话总结 (再)

R1 12h PASS (DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE): 12/12 ckpt, 6 dim 全 row, watchlist 7→7 稳定, 0 forbidden, 0 fake, 0 auto-advance. R1 ≠ edge proven. R1 ≠ can_run_probe_now. 等 user 决定 next stage.
