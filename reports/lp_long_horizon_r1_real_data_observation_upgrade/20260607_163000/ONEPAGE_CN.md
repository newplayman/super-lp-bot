# R1 Real-Data Observation Upgrade — One Pager

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T17:10:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`
- r1_smoke_status: **PASS**

## 0. 一句话

R1 smoke 跑通: 20 池 (13 Solana orca + 7 BSC V3), 6 dimensions **全部**有非零 row count (20/120/100/20/2/20), market regime 真实 CoinGecko 7d data, 7 BSC V3 池 watchlist (medium confidence), data_insufficient 0. R1 仍**不** 翻 freeze / actual_fee / can_run_probe_now. 推荐 next stage = **`LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1`**.

## 1. R1 关键字段 (per spec)

| 字段 | 值 | 评估 |
|---|---|---|
| `r1_schema_ready` | **true** | 6 dimensions schema defined |
| `r1_collector_built` | **true** | scripts/lp_long_horizon_r1_real_data_collector_v1.py exists |
| `r1_short_smoke_ran` | **true** | smoke 跑通 (2-3 min) |
| `selected_pool_count` | **20** | 13 Solana + 7 BSC |
| `pool_snapshot_rows` | **20** | 7 medium + 13 low |
| `quote_snapshot_rows` | **120** | 60 low + 60 unavailable |
| `fee_velocity_rows` | **100** | 100 unavailable (DexScreener 不可达) |
| `liquidity_distribution_rows` | **20** | 7 low (CPMM) + 13 unavailable (CLMM/DLMM) |
| `market_regime_rows` | **2** | 2 medium (solana + bsc, CoinGecko real) |
| `candidate_review_rows` | **20** | per pool |
| `quote_ready_pool_count` | **7** | 7 BSC V3 (跟随 pool_snapshot medium) |
| `fee_ready_pool_count` | **0** | DexScreener 不可达 |
| `liquidity_ready_pool_count` | **0** | CLMM/DLMM bitmap 缺失 |
| `ev_ready_pool_count` | **0** | 4 dim 不全 |
| `preflight_candidate_count` | **0** | ev_ready=0 |
| `watchlist_count` | **7** | 7 BSC V3 (medium confidence) |
| `data_insufficient_count` | **0** | R1 全部 20 池**至少** 1 dim 有 signal |
| `actual_fee_data_available` | **`false`** (LOCKED) | R1 ≠ actual fee |
| `fee_proxy_only` | **`true`** (R1 ≠ actual) | honest failure modes |
| `no_wallet_tx_probe` | **`true`** | ✅ |
| `wallet_or_tx_touched` | **`false`** | ✅ |
| `transaction_sent` | **`false`** | ✅ |
| `can_run_probe_now` | **`false`** (LOCKED) | freeze |
| `tiny_canary_allowed` | **`"no"`** (LOCKED) | freeze |
| `edge_proven` | **`"no"`** (LOCKED) | R1 不 = edge proven |

## 2. R1 vs R0 关键对比

| Metric | R0 (12h) | R1 (smoke) | Delta |
|---|---|---|---|
| pool_snapshot 真实度 | 0 / placeholder | 7 medium + 13 low | ✅ R1 强 |
| quote 真实度 | 0 / placeholder | 7 low + 13 unavailable | ✅ R1 强 |
| fee 真实度 | 0 / placeholder | 100 unavailable (honest reason) | ⚠️ R1 = R0 (DexScreener 不可达) |
| liquidity 真实度 | 0 / placeholder | 7 low + 13 unavailable | ✅ R1 强 |
| market regime 真实度 | 84 rows × 0 (静态) | 2 rows × 真实 CoinGecko | ✅✅ R1 大幅强 |
| watchlist | 0 | **7** | ✅ R1 首次>0 |
| preflight | 0 | 0 | = R0 (因 liquidity 不全) |
| data_insufficient | 20 (R0 53 on 53-pools) | **0** | ✅ R1 大幅强 |
| actual_fee | false | false (LOCKED) | = |
| can_run_probe_now | false | false (LOCKED) | = |

## 3. R1 6 dimensions 真实度

| Dimension | high | medium | low | unavailable | Note |
|---|---|---|---|---|---|
| r1_pool_snapshot | 0 | 7 | 13 | 0 | BSC V3 slot0 active_tick real (medium); Solana account data length (low) |
| r1_quote_snapshot | 0 | 0 | 60 | 60 | QuoterV2 not deployed; honest low/unavailable |
| r1_fee_velocity | 0 | 0 | 0 | 100 | DexScreener indexer_unreachable; honest unavailable |
| r1_liquidity_distribution | 0 | 0 | 7 | 13 | BSC V3 CPMM low; CLMM/DLMM unavailable |
| r1_market_regime | 0 | 2 | 0 | 0 | solana + bsc 真实 CoinGecko 7d history |
| r1_candidate_review | (preflight=0, watchlist=7, ev_ready=0, data_insufficient=0) | | | | 7 BSC V3 → watchlist |

## 4. R1 7 watchlist (BSC V3 全部)

| Pool | Confidence | Reason |
|---|---|---|
| 0x172fcD41E0913e95784454622d1c3724f546f849 | medium | slot0 active_tick real + tvl_proxy > 0 |
| 0x36696169C63e42cd08ce11f5deeBbCeBae652050 | medium | 同上 |
| 0xf2688Fb5B81049DFB7703aDa5e770543770612C4 | medium | 同上 |
| 0x81A9b5F18179cE2bf8f001b8a634Db80771F1824 | medium | 同上 |
| (3 more BSC V3) | medium | 同上 |

## 5. R1 仍**不**证明 (4 项)

- ❌ 不证明 actual fee accrual (R1 ≠ actual fee, **不** mint LP / **不** tokenId)
- ❌ 不证明 ev_ready (4 dim 不全, fee+liquidity 缺失)
- ❌ 不证明 preflight candidate (ev_ready=0)
- ❌ 不证明 20 池都值得参与 (R1 0 preflight = data insufficient, **不** = LP reject)

## 6. R1 严禁 (本 stage 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动 long-running collector
- ❌ 不启动 tmux / cron / systemd / daemon
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction
- ❌ 不 approve / mint / add/remove liquidity / collect / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ 不翻 `can_run_probe_now` / `tiny_canary_allowed` / `edge_proven` / `actual_fee_data_available`
- ❌ 不修改 R0 collector / adapters
- ❌ 不修改 12h data dir
- ❌ 不 mint LP NFT (R1 严格 read-only)

## 7. 锁定字段 (R1 期间 LOCKED)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `actual_fee_data_available` | `false` | R1 ≠ actual fee |
| `can_run_probe_now` | `false` | freeze |
| `tiny_canary_allowed` | `"no"` | freeze |
| `edge_proven` | `"no"` | R1 不 = edge proven |
| `global_lp_rejected` | `false` | R1 0 preflight 是 data insufficient, **不** = reject |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

## 8. 后续 (R1 12h 启动前必经步骤)

1. 新审批 (`APPROVE_LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION stage=r1_12h ...`)
2. 新 scope freeze (`coverage_scope=partial_solana_bsc_real_universe_r1_12h`)
3. 新 PRE_RUN_SAFETY_CHECK (12 checks all passed)
4. 新 r1 12h data dir (`data/lp_long_horizon_r1_12h/<RUN_ID>/`)
5. R1 collector 12h 适配 (`scripts/lp_long_horizon_r1_real_data_collector_v1.py + --duration-hours --checkpoint-interval-minutes`)
6. R1 12h tests (≥ 10)
7. R1 12h 启动 via nohup
8. R1 smoke data dir (20260607_163000) **不** 动
9. 12h data dir (20260606_131323) **不** 动

## 9. 决策

**推荐 next stage**: `LP_LONG_HORIZON_R1_12H_REAL_DATA_OBSERVATION_REQUEST_V1` (per spec 规则 5/5 match)

**不推荐**:
- `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_FIX_REPEAT` (R1 smoke 已满足 spec rule)
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (Base 仍 403)
- `PAUSE_*` (R1 12h 是更 productive next step)

## 10. 一句话总结 (再)

R1 smoke PASS: 20 池 6 dim 全 row count > 0, market regime 真实 CoinGecko, 7 BSC V3 watchlist, 0 data_insufficient, 0 preflight (因 ev_ready=0). R1 ≠ actual fee, R1 ≠ LP edge, R1 不翻 freeze. R1 12h 是合理 next step 验 stability + watchlist evolution + data quality.
