# 12h Node Report Review — One Pager (Partial Real Universe)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`
- status: **PASS** (review pass) + **r0 phase still** (12h data insufficient for LP decision)

## 0. 一句话

12h partial collector 跑通 (gate PASS), 53 池**全部** r0 data_insufficient (100%), preflight=0, watchlist=0, actual_fee_data_available=false, fee_proxy_only=true, candidate_decision_reliable=false. 推荐 next stage = **`LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`** (real-time read-only data layer, **不** mint / **不** freeze reopen / **不** actual fee).

## 1. 12h 关键字段

| 字段 | 值 | 评估 |
|---|---|---|
| 12h gate | PASS | runtime 720, error 0%, data_quality PASS |
| 53 池 coverage | 49 Solana + 4 BSC V3 | real on-chain addresses, 0 placeholder |
| Base chain | 0 池 | public RPC 403 (env blocker) |
| preflight_candidate_count | **0** | r0 算不出 EV |
| watchlist_count | **0** | r0 无 fee/TVL trend |
| data_insufficient_count | **53** (100%) | r0 data layer 不足 |
| reject_count | **0** | r0 不 applied tier_c |
| ev_ready_pool_count | **0** | r0 |
| **sum check** | 0+0+53+0=53 ✅ | 全 53 池 accounted |
| global_lp_rejected | **false** | 12h r0 data insufficient, **不**=reject |
| candidate_decision_reliable | **false** | 无 data → 无 decision |
| actual_fee_data_available | **false** | r0 placeholder |
| fee_proxy_only | **true** | r0 proxy only |
| tier_classifier_output | DEFERRED_TO_R1 | r0 算不出 tier |
| r1_upgrade_required | **true** | R1 **是** 必要 next step |

## 2. 12h 证明了 / 未证明

### 证明了 (8 项)
- ✅ collector 可稳定运行 12h (720 min exact)
- ✅ checkpoint / heartbeat / finalize scheduling 可用
- ✅ real pool address universe 可进入 pipeline (53 池, 0 placeholder)
- ✅ no wallet / tx / probe safety preserved
- ✅ 12h data pipeline stability PASS (error_rate 0.0%)
- ✅ r0 phase smoke_placeholder data layer 透明 (honest flag)
- ✅ auto_advance LOCKED (24h **不** 自动)
- ✅ finalize block 透明 + git automation OK (commit `30b67c4`)

### 未证明 (8 项)
- ❌ 不证明 LP 有正 EV
- ❌ 不证明 LP 没肉
- ❌ 不证明可进入 probe
- ❌ 不证明 actual fee accrual
- ❌ 不证明真实 range / tick / bin fee capture
- ❌ 不证明 53 个池都值得参与
- ❌ 不证明 full chain coverage
- ❌ 不证明 market regime-aware sizing

## 3. Coverage scope (3 levels)

| Level | Observed | Missing | Coverage % |
|---|---|---|---|
| **Chain** | 2 (solana, bsc) | 1 (base) | 66.7% |
| **DEX** | 5 (4 Solana + 1 BSC) | 4 (3 Base + 1 BSC V2) | 55.6% |
| **Pool addresses** | 53 (real on-chain) | 0 | 100% |
| **Data layer (smoke)** | 53 (all r0 smoke) | 0 | 100% |
| **Data layer (actual)** | **0** | 53 | 0% |
| **EV-ready** | **0** | 53 | 0% |

## 4. Fee estimation 当前状态 (大白话)

- **proxy 还是 actual**: **proxy** (smoke_placeholder=true, 全部 0)
- **有没有 tokenId**: **没有** (actual_fee_accrual.token_id=null, 12 ckpt × 1 placeholder)
- **有没有 feeGrowthInside**: **没有** (schema only)
- **有没有 tokensOwed**: **没有** (schema only)
- **有没有 collected fee**: **没有** (schema only)
- **V3/CLMM range 影响 fee?**: r0 不答 (无 tickLower/Upper/active_tick)
- **DLMM bin coverage 影响 fee?**: r0 不答 (无 active_bin_id/bin_step)
- **CPMM fee share?**: r0 不答 (无 reserve0/1/total_supply/volume actual)
- **r0 data 可用于 LP 决策?**: **完全不能** (r0 = 0, 用 0 算 EV = 必然拒绝)

## 5. Candidate review 4 分类

| Category | Count | 含义 |
|---|---|---|
| preflight_candidate | 0 | 无池通过 preflight (因 r0 算不出 EV) |
| watchlist | 0 | 无池进 watchlist (因 r0 无 fee/TVL trend) |
| data_insufficient | **53** | 53 池**全部** data insufficient (100%) |
| reject | 0 | 0 池被 hard reject (因 r0 不 applied tier_c) |

**important**: data_insufficient (53) **不** = reject. 53 池**没**有 candidate 决策. 决策**等**R1.

## 6. R0 → R1 upgrade plan (5+1+1 项)

**R1 目标** (5 项 real + 1 项 schema only + 1 项 volume):
1. **real reserve / liquidity snapshot** (V3/CLMM/CPMM/DLMM)
2. **real quote snapshot** (QuoterV2 staticcall + Pyth USD conversion)
3. **real fee velocity proxy** (DexScreener + tokenId-based diff)
4. **real volume source** (per-ckpt 5 windows 15m/1h/4h/24h/7d)
5. **real range / tick / bin liquidity** (ticks(net) bitmap + bin_array)
6. **market regime classification** (Pyth/CoinGecko 7d sliding window)
7. **actual fee accrual schema 维持 placeholder** (r0 → r1 **不**mint)

**R1 不做** (重要):
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / keypair / signer
- ❌ 不 mint LP / add liquidity
- ❌ 不 actual fee accrual
- ❌ 不 actual tokenId
- ❌ 不接 paid RPC / paid indexer

**R1 推荐任务名**: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`

## 7. Next stage 决策

**推荐**: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1` (per spec 规则: "如果 12h 仍 r0 proxy / smoke_placeholder → 推荐 R1")

**不推荐**:
- `LP_LONG_HORIZON_READONLY_CONTINUOUS_24H_EXTENSION_REQUEST_V1` (24h 仍 r0, 浪费)
- `LP_LONG_HORIZON_COLLECTOR_ADAPTER_COVERAGE_WIRING_FIX_REPEAT` (Base 仍 403, 即便修好仍 r0)
- `PAUSE_*` (备选, R1 升级是**更** productive next step)

## 8. 锁定字段 (LOCKED, R1 期间仍不翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | actual fee 缺失 |
| `global_lp_rejected` | `false` | r0 data insufficient, **不**=reject |
| `actual_fee_data_available` | `false` | r0 placeholder |
| `fee_proxy_only` | `true` | r0 proxy only |
| `candidate_decision_reliable` | `false` | preflight=0, watchlist=0, data_insufficient=53 |
| `r1_upgrade_required` | `true` | R1 **是** 必要 next step |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

## 9. R1 启动前必经步骤

1. 新审批 (新 MANUAL_APPROVAL_RECORDED, phrase: `APPROVE_LP_LONG_HORIZON_R1_REAL_DATA_UPGRADE stage=r1 mode=readonly no_probe=true no_mint=true`)
2. 新 scope freeze (`coverage_scope=partial_solana_bsc_real_universe_r1`)
3. 新 PRE_RUN_SAFETY_CHECK (12 checks)
4. 新 r1 collector / adapters 升级 (R0_TO_R1_DATA_UPGRADE_PLAN_CN.md)
5. 新 r1 tests (red-green-refactor, ≥ 30)
6. 新 r1 启动 via nohup (新 pid, 不与 12h pid 混)
7. 新 r1 data_dir (`data/lp_long_horizon/20260607_XXXXXX_r1/`)
8. 12h data_dir (20260606_131323) **不** 动

## 10. 严禁 (R1 期间)

- ❌ 不启动 24h / 48h / 72h / 7d
- ❌ 不启动并行 collector
- ❌ 不 probe / canary / live / paper
- ❌ 不读 wallet / seed / keypair / signer
- ❌ 不发送 transaction / approve / mint / swap / bridge
- ❌ 不写 production positions
- ❌ 不覆盖 shadow 原始表
- ❌ 不接 paid RPC / paid indexer
- ❌ 不 mint 实际 LP NFT 仓位 (R1 仅升级 data layer)

## 11. 后续

- 12h review 完成 → 推荐 R1 → user 决定
- R1 12h PASS → 重新评估 preflight/watchlist/data_insufficient
- R1 12h PASS + fee_proxy_only=false + data_insufficient ≤ 10 → next stage = R2 (需 freeze reopen)
- R1 12h FAIL → next stage = R1_FAILURE_AUDIT
- R1 12h PASS + freeze 仍 active + no actual fee → next stage = PAUSE

## 12. 一句话总结 (再)

12h r0 phase 跑通, 53 池**全部** data_insufficient, preflight=0, watchlist=0, actual_fee_data_available=false. **不** 满足"12h 已有真实 quote/fee/EV" 条件 → **不** 推荐 24h. **不** 满足 Base RPC reachable 条件 → **不** 推荐 Base fix. **推荐** R1 升级 (real-time read-only data layer, **不** mint / **不** freeze reopen / **不** actual fee). R1 完成后 6 dimensions non-zero → 重新评估 LP 决策.
