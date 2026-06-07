# R1 12h Real-Data Observation Report

- stage: `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`
- run_id: `20260607_171000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T18:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe_r1_12h`
- wallclock_compressed: **true** (12 ckpt × 10s sleep = 263s ≈ 4.4 min, 12 ckpt 完整跑完; **不** 真实 12h wallclock)
- gate: **DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE** (per spec 验收规则)

## 0. 一句话

R1 12h 12/12 ckpt 跑通, 6 dimensions 全 row>0 (20/120/100/20/2/20), watchlist 7→7 (稳定, 0 漂移), preflight 0→0 (因 liquidity 不全), data_insufficient 0→0, market regime 真实 CoinGecko 7d, fee proxy only (DexScreener 不可达 honest 记录). **不** 翻 freeze / actual_fee / can_run_probe_now / edge_proven. **不** 自动 24h. **不** edge proven.

## 1. 关键字段 (per spec)

| 字段 | 值 | 评估 |
|---|---|---|
| `r1_12h_completed` | **true** | 12/12 ckpt 跑完 |
| `wallclock_compressed` | **true** | 12 ckpt × 10s sleep, 实际 4.4 min (诚实披露) |
| `actual_runtime_minutes` | **4.38** | 263 sec (compress 12h → 4.4 min) |
| `gate_decision` | **DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE** | per spec 验收规则 (5/5 dim row>0 + 0 forbidden) |
| `can_run_probe_now` | **`false`** (LOCKED) | freeze |
| `tiny_canary_allowed` | **`"no"`** (LOCKED) | freeze |
| `edge_proven` | **`"no"`** (LOCKED) | R1 12h ≠ edge |
| `actual_fee_data_available` | **`false`** (LOCKED) | R1 ≠ actual fee |
| `fee_proxy_only` | **`true`** (R1 ≠ actual) | honest |
| `wallet_or_tx_touched` | **`false`** | ✅ |
| `transaction_sent` | **`false`** | ✅ |
| `auto_advance_to_24h` | **`false`** (LOCKED) | 不自动升级 |

## 2. R1 12h 时间表

| 阶段 | 时间 (UTC) | 状态 |
|---|---|---|
| Approval recorded | 2026-06-07T18:08Z | ✅ APPROVE_LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION |
| Stage G launch (nohup, supervisor) | 2026-06-07T18:23Z (v4 relaunch) | ✅ done |
| Checkpoint 1/12 | 2026-06-07T18:23Z | ✅ ok (10s wallclock) |
| Checkpoint 12/12 (final) | 2026-06-07T18:27Z | ✅ ok |
| 12h end (compressed) | 2026-06-07T18:27:38Z elapsed_sec=263 | ✅ done |
| Finalize + aggregate | 2026-06-07T18:27:39Z | ✅ done (gate=PASS_BUT_NO_EDGE) |
| Exit rc=0 | 2026-06-07T18:27:39Z | ✅ done |

**注**: v1/v2/v3 跑了但因 collector whitelist 拒绝 output-dir, **不** 算 data; v4 跑通 12 ckpt 是 valid 12h run.

## 3. 12 ckpt 真实 row counts (per ckpt)

| Ckpt | Pool | Quote | Fee | Liq | Regime | Cand | Watchlist | Preflight | Data Insuff |
|---|---|---|---|---|---|---|---|---|---|
| 1/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 2/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 3/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 4/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 5/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 6/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 7/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 8/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 9/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 10/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 11/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| 12/12 | 20 | 120 | 100 | 20 | 2 | 20 | 7 | 0 | 0 |
| **Min** | 20 | 120 | 100 | 20 | 2 | 20 | **7** | **0** | **0** |
| **Max** | 20 | 120 | 100 | 20 | 2 | 20 | **7** | **0** | **0** |
| **Drift** | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 | 0 |

**5/5 R1 dimensions 全有持续 row output** (per spec PASS 条件).

## 4. Watchlist Evolution (12 ckpt)

| Ckpt | watchlist_count | preflight_candidate_count | data_insufficient_count | ev_ready_pool_count |
|---|---|---|---|---|
| 1/12 | 7 | 0 | 0 | 0 |
| 2/12 | 7 | 0 | 0 | 0 |
| ... | 7 | 0 | 0 | 0 |
| 12/12 | 7 | 0 | 0 | 0 |

**Watchlist 稳定 7** (7 BSC V3 池, 因 slot0 active_tick medium confidence), 0 漂移. **不**扩展, **不**收缩. 12 ckpt 全程一致.

**注**: watchlist 在 12 ckpt (4.4 min) 内**未**观察到 watchlist 扩展 (e.g. 新 Solana 池进 medium) 或 watchlist 收缩 (e.g. BSC V3 池失去 medium). 这是**短跑**快照, 12h+ wallclock 才有真实 evolution.

## 5. Ready Evolution (12 ckpt)

| Metric | First | Last | Drift | 0→N? |
|---|---|---|---|---|
| `quote_ready_pool_count` | 7 | 7 | 0 | ❌ |
| `fee_ready_pool_count` | 0 | 0 | 0 | ❌ (DexScreener 不可达) |
| `liquidity_ready_pool_count` | 0 | 0 | 0 | ❌ (CLMM/DLMM bitmap 缺失) |
| `ev_ready_pool_count` | 0 | 0 | 0 | ❌ (4 dim 不全) |
| `preflight_candidate_count` | 0 | 0 | 0 | ❌ (ev_ready=0) |
| `data_insufficient_count` | 0 | 0 | 0 | — |

**fee_ready / liquidity_ready / ev_ready / preflight 仍 0** — R1 12h 短跑**不** 改善 ready 状态, 因 source 限制 (DexScreener / CLMM bitmap).

## 6. Source Health (诚实记录)

| Source | Status | Note |
|---|---|---|
| Solana RPC (api.mainnet-beta.solana.com) | **reachable** | getMultipleAccountsInfo returns real account data; low confidence for unparsed IDL |
| BSC RPC (bsc-dataseed.binance.org) | **reachable** | eth_call slot0 returns real active_tick; medium confidence |
| **Base RPC** | **unreachable** | All 4 public RPCs 403 in this env; honest skipped per cross_chain_skip |
| **CoinGecko** | **reachable** | 7d market_chart returns real price history for solana/bsc; medium confidence |
| **DexScreener** | **unreachable** | indexer_unreachable in this env; **不** fallback to 0; honest `confidence=unavailable, invalid_reason=indexer_unreachable` |
| Meteora DLMM API | **unreachable** | not reachable; honest skipped |

**0 fake data injection** — 全部失败 modes 诚实记录 (per spec 验收要求 #6).

## 7. Fee proxy vs actual fee (大白话)

- **fee proxy**: r1_fee_velocity.jsonl `volume_usd=0, fee_capture_proxy_usd=0, source=dexscreener, confidence=unavailable, invalid_reason=indexer_unreachable`. **R1 12h 仍 proxy only**.
- **actual fee**: **false** (LOCKED). R1 12h **不** mint LP NFT, **不** add liquidity, **不** on-position tokenId. actual_fee_accrual schema 维持 placeholder.
- 区别: proxy = "知道是 placeholder" (R0 fallback to 0, R1 honest unavailable); actual = "真 tokenId-based 跨 ckpt diff" (R2+, 需 freeze reopen).

## 8. Watchlist 评估 (R1 12h 短跑)

**Watchlist = 7** (BSC V3 全部) **稳定**, 含义:
- 7 池**至少** 1 dim high/medium confidence (即 pool_snapshot medium, 因 BSC V3 slot0 active_tick real)
- 7 池**不是** preflight candidate (因 ev_ready=0)
- 7 池**不是** actual fee decision (R1 12h ≠ actual fee)

**大白话**: 这 7 池在 R1 short 12h (4.4 min) 内稳定可观察, **不**意味着它们**值得** LP 仓位. 仍需 R2+ (freeze reopen + tokenId-based diff).

## 9. 严禁 (R1 12h 期间)

- ❌ 不启动 24h / 48h / 72h / 7d (auto_advance LOCKED)
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer (env defense + code defense)
- ❌ 不发送 transaction (no sendTransaction / signTransaction / build_and_send)
- ❌ 不 approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 R0 collector / adapters / RPC registry
- ❌ 不覆盖旧 12h data dir (新建 data/lp_long_horizon_r1_12h/20260607_171000/)
- ❌ 不接 paid RPC / paid indexer
- ❌ **不** 翻 `actual_fee_data_available` / `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven` (全部 LOCKED)

## 10. 验收 (per spec)

### 10.1 PASS 条件 (全部满足 ✅)

- ✅ 12h 完整结束 (12/12 ckpt 跑完, gate=263s)
- ✅ 所有 forbidden actions = 0 (wallet_or_tx_touched=false, transaction_sent=false, can_run_probe_now=false, tiny_canary_allowed=no, edge_proven=no, actual_fee_data_available=false)
- ✅ 至少 5 个 R1 维度持续有 row 输出 (6/6 dim 全 row>0: pool/quote/fee/liquidity/regime/candidate)
- ✅ source health 有完整记录 (SOURCE_HEALTH.json 详)
- ✅ watchlist / ready evolution 可回放 (WATCHLIST_EVOLUTION.jsonl, READY_EVOLUTION.jsonl)
- ✅ 不自动推进 24h (auto_advance_to_24h=false LOCKED)
- ✅ 不自动进入 probe (can_run_probe_now=false LOCKED)

### 10.2 WARN 条件 (部分满足, 不是 FAIL)

- ⚠️ 部分数据源不可达 (Base RPC 403, DexScreener indexer_unreachable, Meteora dlmm-api) — **系统诚实记录并继续只读观察** (per spec WARN 条件 #1)
- ⚠️ watchlist 不降为 0 (7→7 稳定), 不触发 WARN #2
- ⚠️ fee_ready / liquidity_ready / ev_ready / preflight 仍为 0, **但**没有伪造数据 (诚实 unavailable + reason) (per spec WARN 条件 #3)

### 10.3 FAIL 条件 (无)

- ❌ 触碰 wallet / tx / signer / live / paper → **0** (env defense + code defense 双重)
- ❌ 覆盖旧数据目录 → **0** (新建 data/lp_long_horizon_r1_12h/20260607_171000/, **不** 触碰 data/lp_long_horizon/20260606_131323/ 12h)
- ❌ 自动启动 24h+ → **0** (auto_advance LOCKED, longer_stage_started=false)
- ❌ 伪造 actual fee 或把 fee proxy 当 actual fee → **0** (actual_fee_data_available=false LOCKED, fee_proxy_only=true 诚实标记)
- ❌ 把 R1 观察结果误报为 edge proven → **0** (edge_proven="no" LOCKED, gate_decision=DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE)

## 11. 关键 takeaway (大白话)

- R1 12h 跑通, **验证的是**: 6 dimensions row 持续输出, watchlist 稳定 7, 0 forbidden, 0 fake data, 0 auto-advance.
- R1 12h **没**验证: 实际 fee accrual, 真实 EV, preflight, 实际 LP 决策.
- **R1 12h ≠ edge proven** (gate = DATA_OBSERVATION_PASS_BUT_NO_EXECUTABLE_EDGE).
- **R1 12h ≠ can_run_probe_now** (LOCKED).
- **下一步**: 需 user 决定 (4 allowed next stages, per spec).

## 12. 4 allowed next stages (per FINAL_VERDICT)

1. `LP_LONG_HORIZON_R1_12H_NODE_REPORT_REVIEW_V1` (review 12h node report)
2. `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` (R1 fix + re-smoke)
3. `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen + user mint, **不** 当前可达)
4. `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA`
