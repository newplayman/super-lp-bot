# R1 Candidate Interpretation

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T17:10:00Z`
- r1_smoke_ran: true
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话 (大白话)

R1 比 R0 强很多: market regime 是真实 CoinGecko 7d 数据, BSC V3 slot0 真实 active_tick, Solana account 真实存在, watchlist 首次>0 (7 BSC V3 池), data_insufficient 0 (R0 是 53/53). 但 R1 仍**不**证明 actual fee (R1 ≠ actual fee), 仍 0 preflight candidate (因 liquidity 仍 unavailable for CLMM/DLMM), 仍 0 ev_ready (4 dim 不全). 0 preflight **不** 等于"20 池都没肉"或"global LP reject", 这是**数据不全**, **不** 是 EV 算出 ≤ 0.

## 1. R1 数据比 R0 强在哪里 (5 项)

### 1.1 market regime 真实化 (R0 静态 → R1 真实 CoinGecko)

**R0**: 84 rows × 7 regimes × 12 ckpt, 全部 `price_change_pct=0, realized_vol_pct=0, volume_to_tvl_pct=0`, regime 标签**静态**分配 per token_pair.

**R1**: 2 rows × 真实 CoinGecko 7d history:
- `solana`: return_1h=0.30%, return_6h=0.86%, vol1h=3.37%, regime=low_volatility_stable, confidence=medium
- `bsc`: return_1h=0.58%, return_6h=0.29%, vol1h=2.31%, regime=low_volatility_stable, confidence=medium

**强在哪里**: 真实价格历史驱动 regime, **不** 是静态标签. R1 regime 可**真实**反映 market 状态.

### 1.2 pool_snapshot 真实化 (R0 0/null → R1 7 medium + 13 low)

**R0**: 53 池全部 `reserve_a_raw=0, reserve_b_raw=0, liquidity=0, active_tick=null`, smoke_placeholder=true.

**R1**: 7 BSC V3 池 medium (slot0 active_tick 真实 on-chain), 13 Solana 池 low (account data length 真实). R1 表达: 真实 on-chain account exists + (低质量)data length proxy.

**强在哪里**: BSC V3 active_tick 是**真实** current tick, **不** 是 placeholder. Solana account 真实存在 (R0 是 0 fallback; R1 是 low confidence 真实 account).

### 1.3 watchlist 首次>0 (R0 0 → R1 7)

**R0**: watchlist_count=0, 53 池全部 data_insufficient, 没池进 watchlist.

**R1**: watchlist_count=**7** (7 BSC V3 池, 因 high/medium confidence). 13 Solana 池**不**进 watchlist (low confidence, **不** 是 high/medium).

**强在哪里**: 7 池**真实**满足 "basic pool meta + ≥1 high/medium confidence dimension". R0 是 0 因全 smoke_placeholder. R1 watchlist 是**首批**可信 watchlist.

### 1.4 data_insufficient 0 (R0 53/53 → R1 0/20)

**R0**: 53/53 data_insufficient, 100%.

**R1**: 0/20 data_insufficient, 0%. 全部 20 池**至少** 1 dim 有 signal (pool_snapshot low/medium OR quote low OR market_regime medium).

**强在哪里**: R1 全 20 池 6 dim 至少 1 个有 data layer signal. R0 是 53/53 0 signal.

### 1.5 honest failure mode (R0 0 fallback → R1 unavailable + reason)

**R0**: 拿不到 → fallback to 0, smoke_placeholder=true (hides failure).

**R1**: 拿不到 → `confidence=unavailable, invalid_reason=<specific reason>`, **不** fallback to 0, **不** hide failure.

**强在哪里**: R1 失败原因 honest 记录 (rpc_unreachable / indexer_unreachable / pool_address_invalid / adapter_not_implemented). 可**真实**判断是 RPC 问题还是 adapter 问题, **不** 是"全部 0" 模糊状态.

## 2. R1 仍**不**能证明 actual fee accrual (4 项)

### 2.1 R1 仍 0 actual_fee_data_available (LOCKED)

**原因**: R1 范围 = real-time read-only data layer (6 dimensions), **不** mint LP NFT, **不** add liquidity, **不** on-position tokenId. actual_fee schema 维持 placeholder, r0_phase_status 维持 "schema only, no records; r1 requires user-provided tokenId".

**R1 不解决**: actual fee accrual, IL realized vs IL actual, feeGrowthInside 跨 ckpt diff, tokensOwed, collected fee.

**R1 → actual fee 路径**: 需 freeze reopen + user mint 实际 LP NFT 仓位 + 跨 24h+ ckpt tokenId-based diff → 这是 R2, **不** 是 R1.

### 2.2 R1 仍 0 ev_ready (因 4 dim 不全)

**原因**: ev_ready = quote_ready AND fee_ready AND liquidity_ready AND regime_ready. R1 4 dim 状态:
- quote_ready: 7 (BSC V3 跟随 pool_snapshot medium)
- fee_ready: **0** (DexScreener 不可达)
- liquidity_ready: 0 (CLMM/DLMM 仍 unavailable)
- regime_ready: 2 chains (solana + bsc, **不** = per-pool)

**关键**: regime_ready 是 per chain, **不** 是 per pool. per-pool regime_ready = True 仅当此池 chain 在 regime rows 中. R1 regime rows = 2 (solana + bsc), 所以 13 Solana 池 + 7 BSC V3 池 regime_ready=True.

**R1 0 ev_ready 真实原因**: fee_ready=0 (DexScreener 不可达) + liquidity_ready=0 (CLMM/DLMM bitmap 缺失). 两者**均** R1 scope 但 R1 short smoke 不可达, **不** 是"20 池 EV 真 ≤ 0".

### 2.3 R1 仍 0 preflight_candidate

**R1 简化 preflight**: preflight = ev_ready AND TVL proxy > 0. ev_ready=0 → preflight=0. 这**不**是 full EV 计算 (R1 仍**不**算 EV), 是 R1 简化 gate.

**full preflight (R2+)**: EV = fee - IL - gas - rebalance - opportunity_cost. R1 缺 fee + IL, **不** 算 full EV. preflight 仍 deferred.

### 2.4 R1 7 watchlist ≠ 7 preflight candidate

**关键区别**: watchlist 是 "basic meta + ≥1 high/medium confidence" (轻量 gate), preflight 是 "ev_ready + TVL > 0" (重 gate). 7 watchlist ≠ 7 preflight, 因 4 dim 不全.

**大白话**: R1 watchlist = "这池**可能**值得 follow up", R1 preflight = "这池**可以**进入 EV 计算". R1 7 watchlist 是 "follow up 池", **不** 是 "EV-pass 池".

## 3. R1 是否产生 watchlist? 是, 7 池.

### 3.1 7 watchlist 池 (全部 BSC V3)

| Pool | Chain | Protocol | Confidence | Reason |
|---|---|---|---|---|
| 0x172fcD41E0913e95784454622d1c3724f546f849 | bsc | pancakeswap_v3 | medium | slot0 active_tick 真实 + tvl_proxy > 0 |
| 0x36696169C63e42cd08ce11f5deeBbCeBae652050 | bsc | pancakeswap_v3 | medium | 同上 |
| 0xf2688Fb5B81049DFB7703aDa5e770543770612C4 | bsc | pancakeswap_v3 | medium | 同上 |
| 0x81A9b5F18179cE2bf8f001b8a634Db80771F1824 | bsc | pancakeswap_v3 | medium | 同上 |
| (3 more BSC V3) | bsc | pancakeswap_v3 | medium | 同上 |

### 3.2 13 Solana 池**不**进 watchlist (low confidence)

**原因**: Solana pool_snapshot 是 `low` confidence (account data length, **不** 解析 IDL). watchlist gate 需 `high` 或 `medium`, `low` **不** 通过.

**含义**: 13 Solana 池 account 真实存在, 但**没有** real liquidity / tick / fee data. watchlist **不** 包含.

### 3.3 watchlist ≠ preflight ≠ decision

**7 watchlist 是 R1 first 真实 signal**, 但**不**等于 LP decision. 后续:
- R1 12h 扩展: re-evaluate watchlist with full data
- R2 (freeze reopen): actual fee + IL + tokenId → 真实 preflight
- R3 (full LP decision): 实际 mint + position snapshot diff

## 4. R1 是否产生 preflight candidate? 否, 0 池.

### 4.1 0 preflight 真实原因 (数据层)

- 0 ev_ready: fee_ready=0 (DexScreener 不可达) + liquidity_ready=0 (CLMM/DLMM bitmap 缺失)
- ev_ready=0 → preflight=0 (R1 simplified gate)

### 4.2 0 preflight **不**等于 20 池 EV ≤ 0

**大白话**: R1 算不出 EV (因 fee + liquidity 缺失), **不** 是 "20 池 EV 算出来 ≤ 0". 这是**数据层不足**, **不** 是"收益真的负".

**spec 明确**: "**不得**把 R1 data insufficient 解读成 'LP 没肉'". 0 preflight = data insufficient, **不** = LP reject.

### 4.3 R1 → R2 升级路径

- R2: freeze reopen + user mint 实际 LP NFT 仓位 → 拿 tokenId
- R2: 跨 24h+ ckpt tokenId-based diff → 算 actual fee
- R2: liquidity bitmap / bin_array 解析 (R2 升级 IDL or 第三方 SDK)
- R2: DexScreener / on-chain swap event log subscription 替代 DexScreener
- R2 后: 4 dim 全部高 confidence → preflight > 0

## 5. 重要 disclaimer (再)

- ✅ R1 **首次**有真实 market regime data (CoinGecko 7d)
- ✅ R1 **首次**有真实 BSC V3 active_tick (slot0)
- ✅ R1 **首次**watchlist > 0 (7 BSC V3)
- ✅ R1 data_insufficient 0 (vs R0 53/53)
- ❌ R1 仍 0 actual_fee_data_available (LOCKED)
- ❌ R1 仍 0 ev_ready (因 fee + liquidity 不全)
- ❌ R1 仍 0 preflight (因 ev_ready=0)
- ❌ R1 仍 0 fee_velocity (DexScreener 不可达)
- ❌ R1 仍 0 liquidity_distribution (CLMM/DLMM bitmap 缺失)
- ❌ R1 Base 链 0 池 (public RPC 403)
- ❌ R1 **不** = global LP reject
- ❌ R1 **不** = LP edge proven
- ❌ R1 **不** = 实际 fee accrual

## 6. R1 锁定字段 (interpret 期间仍不翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `actual_fee_data_available` | `false` | R1 ≠ actual fee |
| `can_run_probe_now` | `false` | freeze |
| `tiny_canary_allowed` | `"no"` | freeze |
| `edge_proven` | `"no"` | R1 不 = edge proven |
| `global_lp_rejected` | `false` | R1 0 preflight 是 data insufficient, **不** = reject |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
