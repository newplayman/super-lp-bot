# Candidate Review Audit (12h Node Report Review)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

12h r0 phase 跑完, 53 池**全部** `data_insufficient`, preflight_candidate_count=0, watchlist_count=0, reject_count=0. 这**不**等于"53 池都不值得参与", **不** 等于"global LP rejected". 这等于"**数据层不够, 不能做 candidate 决策**". 阻断原因 = DATA_INSUFFICIENT (53/53), **不** 是 REJECT_BY_EV (0/53). 缺 5 个字段组: tokenId + live RPC reserve + live quote + live volume + live regime.

## 1. 候选 review 4 分类 (per spec)

### 1.1 preflight_candidate_count = 0

**含义**: 通过 preflight 资格 (EV > 0 + tier a/b/c + 不在 hard rejection + fee velocity > 阈值) 的池数.

**12h 实际**: **0** 池.

**为什么 0**:
- 53 池 r0_candidate_ready=false (all)
- preflight 资格需 EV > 0, r0 EV = 0 (因 fee=0, IL=null, gas=0, rebalance=0)
- 0 > 0 永远 false → 53 池全部**不**通过 preflight
- 这**不**等于"53 池 EV <= 0", 这等于"53 池 EV **不可计算**" (r0)

### 1.2 watchlist_count = 0

**含义**: 进入 watchlist (基础条件满足, 但需更多数据观察) 的池数.

**12h 实际**: **0** 池.

**为什么 0**:
- watchlist 需 basic pool meta (✅ 53 池有) + recent fee trend (❌ r0 = 0) + TVL trend (❌ r0 = static, 因 reserve=0)
- fee trend 需 24h+ ckpt non-zero fee data
- TVL trend 需 24h+ ckpt non-zero reserve data
- r0 全部 0, watchlist = 0
- 这**不**等于"53 池无 watchlist 价值", 这等于"53 池 **无 watchlist 数据**"

### 1.3 data_insufficient_count = 53

**含义**: 数据层不够, **不** 能做 LP 决策的池数.

**12h 实际**: **53** 池 (= 100%).

**为什么 53**:
- r0 phase fee data = smoke_placeholder (0)
- r0 phase IL data = null
- r0 phase tokenId = null
- r0 phase reserve/liquidity = 0/null
- r0 phase quote = smoke_placeholder (0)
- r0 phase volume = 0
- r0 phase regime = static (not real-time)
- 53 池**全部** 缺 actual data layer

**重要**: DATA_INSUFFICIENT **不** = REJECT_BY_EV. 两者**完全**不同. REJECT_BY_EV = "有 data, EV <= 0, 拒绝". DATA_INSUFFICIENT = "**没有** data, **不能**算 EV, 暂搁置". spec 明确: "**不得** 把 DATA_INSUFFICIENT 解读成 '不值得参与'".

### 1.4 reject_count = 0

**含义**: 被 hard rejection 拒绝的池数 (e.g. tier_c_hard_rejection_policy applied).

**12h 实际**: **0** 池.

**为什么 0**:
- tier_c_hard_rejection_policy **不** applied (因 r0)
- tier_c_assigned = false
- tier_a/b_assigned = false
- hard rejection 需 tier 分类 + 黑名单, 两者**不**存在 r0

**重要**: reject_count=0 **不**意味着"53 池都通过". reject_count=0 + data_insufficient=53 = "53 池**没**reject, **也**没**preflight, 全部**等**data".

## 2. 53 池**每池** data_insufficient 缺什么字段 (5 组)

### 2.1 缺 tokenId (Group 1: position identity)

| 字段 | 缺什么 | 阻塞原因 |
|---|---|---|
| `token_id` | on-position LP NFT id | freeze 不允许 mint LP / add liquidity |
| `pool_address` (在 actual_fee_accrual schema 中) | 池地址 | 缺 (因无 tokenId) |
| `entry_at`, `exit_at` | entry/exit timestamp | 缺 (因无 tokenId) |
| `entry_tick_lower/upper`, `exit_tick_lower/upper` | tick range | 缺 (因无 tokenId) |

**r1 修复需要**: freeze reopen + user mint 实际 LP NFT 仓位 → 拿 tokenId → 读 `positions(tokenId)` → 拿 tickLower/tickUpper.

### 2.2 缺 live RPC reserve / liquidity / tick (Group 2: pool state)

| 字段 | 缺什么 | 阻塞原因 |
|---|---|---|
| `reserve_a_raw`, `reserve_b_raw` | CPMM reserve (Raydium CPMM, PancakeSwap V2) | no live RPC (env + freeze) |
| `liquidity` | V3/CLMM liquidity | no live RPC |
| `active_tick` | V3/CLMM current tick | no live RPC |
| `active_bin` | DLMM current bin | no live RPC + dlmm-api 不可达 |
| `feeGrowthGlobal0/1` | V3/CLMM global fee growth | no live RPC |
| `tick_spacing` | V3/CLMM tick spacing | no live RPC |
| `bin_step` | DLMM bin step | no live RPC + dlmm-api 不可达 |

**r1 修复需要**: live RPC (Solana mainnet + BSC + Base). Base 需 env change or paid RPC (paid blocked by freeze).

### 2.3 缺 live quote (Group 3: quote data)

| 字段 | 缺什么 | 阻塞原因 |
|---|---|---|
| `amount_in_raw` (actual) | QuoterV2 staticcall amount in | no live RPC |
| `amount_out_raw` (actual) | QuoterV2 staticcall amount out | no live RPC |
| `price_impact_pct` (actual) | actual price impact | no live quote |
| `slippage_pct` (actual) | actual slippage | no live quote |
| `fee_usd` (actual) | actual fee in USD | no live quote + no price |

**r1 修复需要**: live QuoterV2 (Solana / BSC) + Pyth price oracle (USD conversion).

### 2.4 缺 live volume (Group 4: volume / fee velocity)

| 字段 | 缺什么 | 阻塞原因 |
|---|---|---|
| `volume_proxy_usd` (actual) | on-chain swap event Σamount × price | no volume indexer (DexScreener/GeckoTerminal/on-chain event) |
| `fee_capture_proxy_usd` (actual) | actual fee captured in window | no tokenId + no live quote |
| `sample_count` (actual) | on-chain swap event count | no volume indexer |

**r1 修复需要**: DexScreener / GeckoTerminal / on-chain swap event log subscription + tokenId-based feeGrowthInside diff.

### 2.5 缺 live regime (Group 5: market regime)

| 字段 | 缺什么 | 阻塞原因 |
|---|---|---|
| `price_change_pct` (actual) | 7d lookback price change | no real-time price feed (Pyth/CoinGecko not integrated) |
| `realized_vol_pct` (actual) | 7d realized volatility | 同上 |
| `volume_to_tvl_pct` (actual) | 24h volume / TVL | no volume indexer |
| `incentive_active` (actual) | real-time incentive program status | no on-chain program query |

**r1 修复需要**: Pyth/CoinGecko 集成 + on-chain incentive program query (Merkl/Aerodrome/etc.).

## 3. 53 池**不**是"reject by EV" 是 "data insufficient"

**大白话**:
- 53 池**不**是 "EV <= 0, 拒绝" (因 r0 算不出 EV)
- 53 池**不**是 "tier_c hard reject" (因 r0 算不出 tier)
- 53 池**不**是 "fee 太低, 拒绝" (因 r0 fee=0 是 placeholder, **不**是实际)
- 53 池**不**是 "IL 太高, 拒绝" (因 r0 IL=null)
- 53 池**不**是 "tick out of range, 拒绝" (因 r0 tick=null)
- 53 池**是** "**没有** data, **不能**做 LP 决策, 暂搁置等 r1"

**spec 明确**: "**不得** 把 DATA_INSUFFICIENT 解读成 '不值得参与'". 任何把 53 池判为"不参与"的解读 = **错误**解读.

## 4. global_lp_rejected = false (重要)

**含义**: global_lp_rejected = "12h 跑通后, LP 全局**被**拒绝" (因 r0 阻断所有池). 12h review 明确: **不** = global_lp_rejected.

**为什么 false**:
- 12h 跑通 ≠ LP rejected
- 12h r0 = data insufficient, **不** = reject
- LP rejected 仅在: 1) freeze reopened, 2) r1 actual data, 3) preflight all reject by EV (≥ N ckpt)
- 当前 3 个条件**全部** false → global_lp_rejected = false
- 这是**未** 拒绝 LP, 是**未** 接受 LP, 是**未**做决定

**重要**: global_lp_rejected = false **不**等于"LP 可以". false 仅指"未做 global reject 决定". 实际 LP **不**可进 (因 freeze + r0 + data insufficient), 但**理由**是 "blocked by r1 upgrade + freeze", **不**是 "global reject".

## 5. candidate_decision_reliable = false

**含义**: candidate review 决策**是**否 reliable (有 data, 可信).

**12h 实际**: **false**.

**为什么 false**:
- 53 池 data_insufficient (100%)
- preflight=0, watchlist=0, reject=0 → "no decision" 状态
- r0 data layer = 0 → "no data to base decision on"
- 任何"53 池参与"或"53 池不参与"决策 = unreliable (因无 data)
- candidate_decision_reliable = false **不**意味着"reject by unreliable", 是 "**不**做 candidate 决策, 等 r1"

## 6. tier_classifier_output = DEFERRED_TO_R1

**含义**: tier 分类 (a/b/c) **是否** applied.

**12h 实际**: **DEFERRED_TO_R1** (per spec).

**为什么 DEFERRED**:
- tier 分类需 actual fee + TVL trend + tokenId-based risk + IL data
- 53 池 actual fee = 0 (r0 placeholder)
- 53 池 TVL trend = static (因 reserve=0)
- 53 池 tokenId-based risk = 0 (无 tokenId)
- 53 池 IL = null
- 全部 4 个 component 不足 → tier 分类**不** applied → DEFERRED_TO_R1

**r1 修复需要**: r1 actual data → tier classifier output = tier_a/b/c (具体).

## 7. watchlist 实际状态

**12h 实际**: 0 池.

**为什么 0**:
- watchlist 需 basic pool meta + recent fee trend + TVL trend
- basic pool meta ✅ 53 池有 (来自 prior stage CSVs)
- recent fee trend ❌ r0 = 0 × 12 ckpt = 0
- TVL trend ❌ r0 = static (因 reserve=0)
- 0 + 0 → 0 池进 watchlist

**r1 修复需要**: r1 actual fee + TVL trend → 重新计算 watchlist.

## 8. 关键 takeaway

| Metric | 值 | 含义 |
|---|---|---|
| preflight_candidate_count | **0** | 无池通过 preflight (因 r0 算不出 EV) |
| watchlist_count | **0** | 无池进 watchlist (因 r0 无 fee/TVL trend) |
| data_insufficient_count | **53** | 53 池**全部** data insufficient (100%) |
| reject_count | **0** | 0 池被 hard reject (因 r0 不 applied tier_c) |
| **总和** | **53** | preflight (0) + watchlist (0) + data_insufficient (53) + reject (0) = 53 ✅ |
| global_lp_rejected | **false** | **不** = "53 池 rejected"; **不** = "53 池 accepted"; **不** = "53 池 decision made" |
| candidate_decision_reliable | **false** | **不**做 candidate 决策, 等 r1 |

**重要**: data_insufficient (53) **不**是 reject. 53 池**没**有 candidate 决策. 决策**等**r1.

## 9. 锁定字段 (LOCKED)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | r0 + freeze |
| `tiny_canary_allowed` | `"no"` | r0 + freeze |
| `edge_proven` | `"no"` | r0 phase |
| `global_lp_rejected` | `false` | data insufficient, **不** = reject |
| `actual_fee_data_available` | `false` | r0 placeholder |
| `fee_proxy_only` | `true` | r0 proxy only |
| `candidate_decision_reliable` | `false` | preflight=0, watchlist=0, data_insufficient=53 |
| `preflight_candidate_count` | 0 | r0 |
| `watchlist_count` | 0 | r0 |
| `data_insufficient_count` | 53 | r0 (100%) |
| `r1_upgrade_required` | `true` | r0 → r1 mandatory before any LP decision |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
