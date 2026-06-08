# R1 12h Full Wallclock — What Data Can Be Reused (CN)

- **stage**: `LP_LONG_HORIZON_R1_PAUSE_AND_FREEZE_RECORD_V1`
- **status**: PAUSED
- **source_data_dir**: `/opt/lpbot/lp-bot-v3-origin-check/data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500`
- **purpose**: 文档化 PAUSE 期间哪些 data 可被 future re-aggregation / re-analysis 复用, 哪些不能, 哪些是新 stage 必须重新采集的

## 0. 一句话

R1 12h v3 (RUN_ID `20260607_191500`) 11h 5m 的真实 observation data 有 observational value, 但**不能**用于 edge claim. PAUSE 期间 data dir 不删不改; future reopen 时, 决定哪些 data 可被 re-aggregation 复用时, 应按本文档分类.

## 1. 可被复用 (reusable) 的 data

### 1.1 Pool snapshots (12 ckpt × 20 pools = 240 records)

- **目录**: `data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500/checkpoint_*/r1_pool_snapshot.{csv,json}`
- **schema**: pool address, token0/token1, fee tier, liquidity, sqrt_price_x96, current_tick, tvl, volume_24h, fees_24h
- **chain coverage**: solana (Raydium CLMM, Orca Whirlpool, Meteora) + bsc (PancakeSwap V3)
- **chain skipped**: base (all 4 public RPCs 403)
- **真实度**: real on-chain data via public RPC (api.mainnet-beta.solana.com, bsc-dataseed.binance.org, solana.publicnode.com)
- **可复用**: ✅
  - 任何 future "pool universe 稳定性" 跨 run 对比
  - 任何 future "tvl/volume 演化" 跨 run 对比
  - 任何 future "selected_pool_count=20 universe 一致性" 检查
  - **不** 用于 edge claim (没 actual fee data)

### 1.2 Quote snapshots (12 ckpt × 120 quotes = 1440 records)

- **目录**: `checkpoint_*/r1_quote_snapshot.{csv,json}`
- **schema**: pool address, side (bid/ask), price, size, source (jupiter, raydium, pancakeswap router)
- **真实度**: real quote API
- **可复用**: ✅
  - 任何 "quote spread" 跨 run 对比
  - 任何 "quote staleness" 分析
  - 任何 "quote coverage" 检查 (20 pool × 6 quote source = 120 per ckpt)

### 1.3 Liquidity distribution (12 ckpt × 20 pools = 240 records)

- **目录**: `checkpoint_*/r1_liquidity_distribution.{csv,json}`
- **schema**: pool address, tick_lower, tick_upper, liquidity_amount
- **真实度**: real on-chain via tick bitmap scan
- **可复用**: ✅
  - 任何 "流动性集中度" 跨 run 对比
  - 任何 "depth chart" 离线重建
  - 任何 "out-of-range 比例" 长期跟踪

### 1.4 Market regime (12 ckpt × 2 regime = 24 records)

- **目录**: `checkpoint_*/r1_market_regime.{csv,json}`
- **schema**: timestamp, regime_class (trending/ranging/volatile), confidence
- **真实度**: derived from on-chain volatility + volume; honest if derive logic transparent
- **可复用**: ✅
  - 任何 "regime transition" 跨 run 对比
  - 任何 "regime persistence" 分析
  - **不** 用于 edge claim

### 1.5 Watchlist evolution (12 ckpt × 7 watchlist pools = 84 records)

- **目录**: `reports/lp_long_horizon_r1_12h_full_wallclock_observation/20260607_191500/WATCHLIST_EVOLUTION.{json,jsonl}`
- **schema**: ckpt, watchlist_count, preflight_candidate_count, data_insufficient_count, ev_ready_pool_count, quote_ready_pool_count, fee_ready_pool_count, liquidity_ready_pool_count
- **观察**: ckpt 1 → ckpt 12: 7 → 7 (稳定, 0 漂移); ev_ready=0, fee_ready=0 (因为 fee_proxy_only)
- **可复用**: ✅
  - 任何 "watchlist 稳定性" 跨 run 对比
  - 任何 "watchlist 准入 funnel" 分析
  - 任何 "fee_ready=0 ⇒ fee_proxy_only" 状态 sanity check

### 1.6 Source health (12 ckpt × chain reachability)

- **目录**: `reports/.../SOURCE_HEALTH.json`
- **schema**: per-ckpt solana/bsc/base reachability + chains_skipped
- **观察**: solana=reachable, bsc=reachable, base=unreachable (all 4 endpoints 403)
- **可复用**: ✅
  - 任何 future "base RPC reachability 趋势" 跨 run 对比
  - 任何 future "paid RPC 是否值得接" 决策证据

### 1.7 Wrapper / supervisor logs (line-by-line)

- **目录**: `reports/.../supervisor_nohup.log`, `wrapper_nohup_v3.log`
- **可复用**: ✅
  - 任何 future "supervisor 行为 replay" 用于 fix verification
  - 任何 future "loop topology 分析" 用于 fix A/B/C 决策

## 2. **不**可复用 (NOT reusable) 的 data

### 2.1 Fee velocity (12 ckpt × 100 records = 1200 records)

- **目录**: `checkpoint_*/r1_fee_velocity.{csv,json}`
- **schema**: pool address, time_window, fee_collected, fee_velocity_per_hour
- **真实度**: ❌ **PROXY ONLY** (`fee_proxy_only=true`, `actual_fee_data_available=false`)
- **不可复用**: ❌
  - v3 fee velocity 是基于 **volume × fee_tier** 估算, 不是 actual on-chain fee accrual
  - 任何 R2 stage (actual fee accrual) **必须** 重新采集 actual on-chain fee data
  - v3 fee data **不可** 用于 calibration, **不可** 用于 actual fee 推断, **不可** 与 R2 actual fee data 合并
  - 任何 future "fee yield 估计" 应该标注 "(proxy, not actual)"

### 2.2 Candidate review (12 ckpt × 20 pools = 240 records)

- **目录**: `checkpoint_*/r1_candidate_review.{csv,json}`
- **schema**: pool address, ev_score, fee_score, liquidity_score, regime_score, total_score, recommendation
- **真实度**: derived from pool/quote/liquidity/regime + fee_proxy; total_score 含 fee_proxy 项
- **不可复用**: ⚠️ **部分可, 但 fee 维度必须 discard**
  - candidate_review.total_score **不可** 跨 run 直接对比 (含 fee_proxy)
  - 拆开维度后: ev_score, liquidity_score 可对比; fee_score 不可对比
  - future reuse 应**重算** total_score 用 R2 actual fee

### 2.3 Aggregate summary (in data dir logs/)

- **目录**: `data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500/logs/aggregate_summary.json`
- **内容**: aggregated per-ckpt summary
- **不可复用**: ⚠️ **部分可, 含 calibration 矛盾**
  - `actual_runtime_valid_for_12h_gate=true` 用 660min (= 11h) 作为内部 threshold, **与** report-level 43200s (= 12h) **矛盾**
  - aggregate 内部 threshold 是 supervisor 的 calibration, 较松
  - 任何 future reuse 应以 **report-level 43200s** 为准, 不用 aggregate internal threshold
  - 详见 `WALLCLOCK_FAILURE_CAUSE.md` §4

## 3. 必须重新采集 (must recapture) 的 data

### 3.1 Actual on-chain fee accrual (R2 territory)

- **当前状态**: `actual_fee_data_available=false`, `fee_proxy_only=true`
- **必须**: R2 stage 通过 fee accrual adapter 拉取 actual on-chain fee
- **不能** 用 v3 fee_proxy 数据替代
- **不能** 用 v3 fee_proxy 推断 actual fee
- **不能** 把 v3 fee_proxy + R2 actual_fee 合并 (方法论不一致)

### 3.2 Base chain data (skipped due to RPC 403)

- **当前状态**: `chains_skipped=["base"]` for all 12 ckpts
- **原因**: base public RPC 全部 403
- **必须重新采集** IF user 决定 (a) 接 paid base RPC, 或 (b) 找到 free public base RPC
- **不必须** if user 接受 "R1 仅 solana+bsc universe" 作为新 design

### 3.3 12h+ wallclock data

- **当前状态**: v3 duration=39917s, 不到 12h
- **必须重新采集** IF user 决定 reopen R1 12h research thread with supervisor fix
- **不必须** if user 决定 PAUSE 永久化, redirect 到 engineering

### 3.4 Dexscreener data (skipped due to indexer_unreachable)

- **当前状态**: `dexscreener=unreachable (indexer_unreachable in this env, honest skipped)`
- **必须重新采集** IF environment 改善 或换 endpoint
- **不必须** if user 接受 "no dexscreener" 作为 universe design

### 3.5 Meteora DLMM API data (skipped)

- **当前状态**: `meteora_dlmm_api=unreachable`
- **必须重新采集** 同上

## 4. data dir 保护 (PAUSE 期间)

| data dir | PAUSE 期间动作 | 备注 |
|---|---|---|
| `data/lp_long_horizon_r1_12h_full_wallclock/20260607_191500/` (v3) | **只读, 不删, 不改** | 156 r1_* files + logs/, 保留以备 future re-aggregation |
| `data/lp_long_horizon_r1_12h_full_wallclock/20260607_184500/` (v1 partial) | **只读, 不删, 不改** | 8 files, preserved per no-touch invariant |
| `data/lp_long_horizon_r1_12h_compressed/20260607_171000/` (R1 12h compressed) | **只读, 不删, 不改** | no-touch invariant |
| `data/lp_long_horizon_r1_12h_smoke/20260607_163000/` (smoke) | **只读, 不删, 不改** | no-touch invariant |
| `data/lp_long_horizon_12h/20260606_131323/` (old 12h smoke) | **只读, 不删, 不改** | no-touch invariant |
| `data/lp_long_horizon_*/<other>` | **只读, 不删, 不改** | no-touch invariant |

**严禁** PAUSE 期间 (a) 删任何 data dir, (b) 改任何 ckpt 文件, (c) 移动 data dir, (d) 重新生成 aggregate_summary.json.

## 5. 复用时的 sanity check 清单

任何 future 复用 v3 data 的 stage, 必须先通过这些 sanity check:

1. **可复用 data** 引用时, 在新 stage 文档中明确标 "from v3 RUN_ID 20260607_191500 (proxy = no for pool/quote/liquidity/regime/watchlist/source_health, proxy = yes for fee_velocity)"
2. **不可复用 data** 引用时, **禁止** cross-run comparison of total_score 或 fee_yield
3. **重新采集** 部分明确标 "must recapture in new stage, not reuse v3"
4. **calibration 矛盾** (aggregate internal threshold vs report-level 43200s) 在新 stage 中以 report-level 为准
5. **forbidden actions recheck** 仍 must pass (per `FORBIDDEN_ACTIONS_LOCK.json`)

## 6. 一句话

v3 data 真实, 但只是 **11h 5m observation window**, **不可** 用于 edge claim. PAUSE 期间 data dir 全部 read-only. future reuse 应按本文档分类: pool/quote/liquidity/regime/watchlist/source_health/wrapper log **可** 复用, fee_velocity/candidate_review_total **不可** 复用, base chain / actual fee / 12h+ / dexscreener / meteora_dlmm_api **必须** 重新采集. 任何复用必须通过 5 条 sanity check.
