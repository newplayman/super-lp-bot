# R1 Short Smoke Result

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- executed_at_utc: `2026-06-07T17:05:41Z`
- coverage_scope: `partial_solana_bsc_real_universe` (Base chain unreachable, honest skipped)
- r1_smoke_ran: **true**
- r1_smoke_status: **PASS**

## 0. 一句话

R1 smoke 跑通: 20 池 (13 Solana orca_whirlpool + 7 BSC pancakeswap_v3), Base chain 不可达 honest skipped. 7 BSC V3 池拿回真实 on-chain slot0 active_tick (medium confidence), 13 Solana 池走 getMultipleAccountsInfo 拿回 data length (low confidence, real account exists). 2 chain 真实 CoinGecko market regime (solana/bsc 7d history). 7 watchlist, 0 data_insufficient, 0 preflight_candidate, 0 ev_ready. R1 ≠ actual fee, **不** 翻 freeze.

## 1. R1 smoke 关键统计 (per spec required fields)

| 字段 | 值 | 评估 |
|---|---|---|
| `r1_smoke_ran` | **true** | ✅ smoke 跑通 |
| `selected_pool_count` | **20** | 13 Solana + 7 BSC |
| `pool_snapshot_rows` | **20** | 全部 20 池, **不** 是 0 |
| `quote_snapshot_rows` | **120** | 20 × 6 notional, **不** 是 0 |
| `fee_velocity_rows` | **100** | 20 × 5 windows, **不** 是 0 |
| `liquidity_distribution_rows` | **20** | per pool, **不** 是 0 |
| `market_regime_rows` | **2** | 2 chain (solana + bsc), Base skipped |
| `candidate_review_rows` | **20** | per pool, **不** 是 0 |
| `quote_ready_pool_count` | **7** | 7 BSC V3 (跟随 pool_snapshot medium) |
| `fee_ready_pool_count` | **0** | DexScreener 不可达 → 全部 unavailable |
| `liquidity_ready_pool_count` | **0** | CPMM/CLMM/DLMM 仍 0 (heuristic not implemented) |
| `ev_ready_pool_count` | **0** | 4 dim 不全 |
| `preflight_candidate_count` | **0** | ev_ready=0 → 0 preflight |
| `watchlist_count` | **7** | 7 BSC V3 (high/medium confidence) |
| `data_insufficient_count` | **0** | R1 全部 20 池**至少** 1 dim 有 signal (vs R0 53/53 data_insufficient) |
| `actual_fee_data_available` | **`false`** (LOCKED) | R1 ≠ actual fee |
| `fee_proxy_only` | **`true`** (LOCKED, R1 ≠ actual) | R1 smoke 真实数据但 actual_fee 仍 missing |
| `no_wallet_tx_probe` | **`true`** | ✅ |
| `wallet_or_tx_touched` | **`false`** | ✅ |
| `transaction_sent` | **`false`** | ✅ |
| `can_run_probe_now` | **`false`** (LOCKED) | freeze |
| `tiny_canary_allowed` | **`"no"`** (LOCKED) | freeze |
| `edge_proven` | **`"no"`** (LOCKED) | actual fee 缺失 |

## 2. R1 6 dimensions 真实度评估

### 2.1 r1_pool_snapshot (20 rows)

| Confidence | Count | 含义 |
|---|---|---|
| `high` | 0 | 需 multiple on-chain calls 验证 (R1 短跑, **不** 强求) |
| `medium` | **7** | BSC V3 eth_call slot0 拿回 active_tick (one call, parsed) |
| `low` | **13** | Solana getMultipleAccountsInfo 拿回 data length (account exists) |
| `unavailable` | 0 | (R0 是 100% unavailable / 0 fallback; R1 升级) |

**R1 强于 R0**:
- R0: 全部 0 reserve/liquidity/active_tick, smoke_placeholder=true
- R1: 7 medium (BSC V3 active_tick real) + 13 low (Solana account data real)
- R1 reserve0/1 仍 0 (因 short smoke **不** 解析 IDL 拿 reserve; **不** 是 fallback, 是 R1 scope)
- R1 诚实标记: 0 reserve = "R1 smoke 不解析 reserve", **不** = "0 reserve 是事实"

### 2.2 r1_quote_snapshot (120 rows)

| Confidence | Count | 含义 |
|---|---|---|
| `unavailable` | 60 | 跟随 pool_snapshot unavailable (R0 全 unavailable) |
| `low` | 60 | 跟随 pool_snapshot low/medium, 但 quote_method=unavailable_no_quoter_v2 |

**R1 强于 R0**:
- R0: 120 rows 全 0, smoke_placeholder=true
- R1: 60 low (pool exists, quote adapter missing) + 60 unavailable (R1 explicit)
- R1 诚实标记: QuoterV2 未部署 in this env, **不** = "0 quote 是事实"

### 2.3 r1_fee_velocity (100 rows)

| Confidence | Count | 含义 |
|---|---|---|
| `medium` | 0 | DexScreener 不可达 → 0 |
| `unavailable` | **100** | DexScreener indexer_unreachable |

**R1 弱于期望**:
- DexScreener 全部 indexer_unreachable (公网 API 触发 rate limit 或 DNS 不可达 in this env)
- R1 诚实标记: `confidence=unavailable, invalid_reason=indexer_unreachable`
- **不** fallback to 0 placeholder (R0 是 fallback; R1 是 honest unavailable)

**注**: 12h R0 fee_velocity 也是 0 (smoke_placeholder), 同样 unavailable. R1 **不** 改 fee 数字, **改** 表达方式 (从 `smoke_placeholder=true` 到 `confidence=unavailable, invalid_reason=indexer_unreachable`).

### 2.4 r1_liquidity_distribution (20 rows)

| Confidence | Count | 含义 |
|---|---|---|
| `low` | 7 | BSC V3 CPMM (full_range, in_range_share=1.0 honest low) |
| `unavailable` | 13 | Solana CLMM (tick_range, needs bitmap) + DLMM (bin_range, needs bin_array) |

**R1 强于 R0**:
- R0: 20 rows 全 0, smoke_placeholder=true
- R1: 7 low (CPMM heuristic) + 13 unavailable (CLMM/DLMM honest)
- R1 诚实标记: tick/bin bitmap 解析需 IDL, **不** = "0 liquidity 是事实"

### 2.5 r1_market_regime (2 rows)

| Confidence | Count | 含义 |
|---|---|---|
| `medium` | **2** | solana + bsc 真实 CoinGecko 7d history (return_1h / return_6h / vol1h / regime_label) |
| `unavailable` | 0 | Base chain 不可达 → 整体 skip, **不** 写 row |

**R1 强于 R0**:
- R0: 84 rows (7 regimes × 12 ckpt) 全 0, 静态分配
- R1: 2 rows 真实 CoinGecko data (solana: return_1h=0.30%, return_6h=0.86%, vol1h=3.37%, regime=low_volatility_stable; bsc: return_1h=0.58%, return_6h=0.29%, vol1h=2.31%, regime=low_volatility_stable)
- R1 真实从 public CoinGecko API 拉 7d price history
- R1 诚实标记: Base 不在 row, 因为 unreachable (per `chains_skipped=["base"]`)

### 2.6 r1_candidate_review (20 rows)

| Status | Count | 含义 |
|---|---|---|
| `preflight_candidate=true` | **0** | ev_ready=0 → 0 preflight (R1 simplified preflight) |
| `watchlist=true` | **7** | 7 BSC V3 (high/medium confidence) |
| `data_insufficient=true` | **0** | R1 全部 20 池**至少** 1 dim 有 signal |
| `ev_ready=true` | **0** | 4 dim 不全 (liquidity 仍 unavailable for CLMM/DLMM) |

**R1 强于 R0**:
- R0: preflight=0, watchlist=0, data_insufficient=20 (vs 53), ev_ready=0
- R1: preflight=0, watchlist=7 (**首次**>0), data_insufficient=0 (从 20 → 0), ev_ready=0

**关键**: data_insufficient 0 是**好**信号, 但**不**等于"20 池都值得参与". 7 watchlist 是 BSC V3 池因 slot0 active_tick medium confidence. preflight=0 仍因 liquidity 不全.

## 3. R1 锁定字段 (R1 smoke 期间)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `r1_schema_ready` | `true` | 6 dimensions schema 已定义 |
| `r1_collector_built` | `true` | scripts/lp_long_horizon_r1_real_data_collector_v1.py exists |
| `r1_short_smoke_ran` | `true` | smoke command executed, 13 files written |
| `actual_fee_data_available` | `false` | R1 ≠ actual fee (LOCKED) |
| `can_run_probe_now` | `false` | freeze |
| `tiny_canary_allowed` | `"no"` | freeze |
| `edge_proven` | `"no"` | R1 不 = edge proven |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

## 4. R1 vs R0 关键对比

| Metric | R0 (12h 跑完) | R1 (smoke 跑完) | Delta |
|---|---|---|---|
| pool_snapshot 真实度 | 0 / placeholder | 7 medium + 13 low | ✅ R1 强 |
| quote 真实度 | 0 / placeholder | 7 low + 13 unavailable | ✅ R1 强 |
| fee 真实度 | 0 / placeholder | 100 unavailable (honest reason) | ⚠️ R1 = R0 (DexScreener 不可达) |
| liquidity 真实度 | 0 / placeholder | 7 low (CPMM) + 13 unavailable | ✅ R1 强 |
| market regime 真实度 | 84 rows × 0 (静态) | 2 rows × 真实 CoinGecko | ✅✅ R1 大幅强 |
| watchlist | 0 | **7** | ✅ R1 首次>0 |
| preflight | 0 | 0 | = R0 (因 liquidity 不全) |
| data_insufficient | 20 (= R0 53 on 53-pools subset) | **0** | ✅ R1 大幅强 |
| actual_fee | false | false (LOCKED) | = |
| can_run_probe_now | false | false (LOCKED) | = |

## 5. R1 严禁 (本 smoke 期间)

- ❌ 不启动 24h / 48h / 72h / 7d (smoke only, 2-3 min)
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction
- ❌ 不 approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ 不写真实 secret
- ❌ can_run_probe_now 维持 false
- ❌ tiny_canary_allowed 维持 "no"
- ❌ edge_proven 维持 "no"
- ❌ actual_fee_data_available 维持 false
- ❌ 不修改 R0 collector / adapters
- ❌ 不修改 12h data dir
