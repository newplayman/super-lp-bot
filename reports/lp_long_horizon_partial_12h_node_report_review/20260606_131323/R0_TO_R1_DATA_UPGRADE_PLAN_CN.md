# R0 → R1 Data Upgrade Plan (12h Node Report Review)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话

R0 phase 跑完验证 pipeline 稳定, 但 r0 data layer 全部 smoke_placeholder (53 池 fee=0, IL=null, tokenId=null, reserve=0). R1 目标: 接入 **live RPC** (real reserve/liquidity) + **real quote** (QuoterV2) + **real volume** (DexScreener/on-chain swap) + **real regime** (Pyth/CoinGecko) + **on-position tokenId schema ready** (仍 schema only, 实际 mint 仍 blocked by freeze). 推荐下一 stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`.

## 1. R1 目标 (5 项)

### 1.1 real reserve / liquidity snapshot (V3/CLMM/CPMM/DLMM)

**当前 (R0)**: pool_snapshots.jsonl `reserve_a_raw=0, reserve_b_raw=0, liquidity=0, active_tick=null, active_bin=null`.

**R1 目标**: pool_snapshots.jsonl 填**真实** on-chain reserve / liquidity / tick / bin.

**实现**:
- **Solana CLMM (Orca/Raydium)**: `getMultipleAccountsInfo` 读 Whirlpool / Raydium CLMM 状态 account → 解析 `sqrt_price`, `tick_current_index`, `liquidity`
- **Solana CPMM (Raydium CPMM)**: `getMultipleAccountsInfo` 读 Raydium CPMM pool state → 解析 `reserve_a_amount`, `reserve_b_amount`
- **Solana DLMM (Meteora)**: dlmm-api (env 不可达) or DexScreener API → 解析 `active_id`, `bin_step`, `bin_liquidity[]`
- **BSC V3 (PancakeSwap)**: eth_call `slot0(pool)` + `liquidity(pool)` → 解析 `sqrtPriceX96`, `tick`, `liquidity`
- **BSC V2 (PancakeSwap, currently 0 pool)**: eth_call `getReserves(pair)` → 解析 `reserve0`, `reserve1`, `blockTimestampLast`
- **Base (currently 0 chain)**: 同 BSC, 但 Base 需 env change (public RPC 403) or paid RPC (freeze blocks)

**R1 deliverable**:
- pool_snapshots.jsonl: `reserve_a_raw, reserve_b_raw, liquidity, active_tick, active_bin, feeGrowthGlobal0/1, tick_spacing, bin_step` 全部填**真实**值
- per-ckpt 53 池 × 12 ckpt = 636 行, 全部非 0

### 1.2 real quote snapshot (QuoterV2 staticcall)

**当前 (R0)**: quote_snapshots.jsonl `amount_in_raw=0, amount_out_raw=0, price_impact_pct=0, slippage_pct=0, fee_usd=0`.

**R1 目标**: quote_snapshots.jsonl 填**真实** QuoterV2 staticcall 结果.

**实现**:
- **Solana CLMM**: Whirlpool `quote_swap` / Raydium CLMM `quote` instruction (走 simulate, **不**走 sendTransaction) → 解析 amount_out
- **BSC V3**: eth_call `IQuoterV2.quoteExactInputSingle(tokenIn, tokenOut, fee, amountIn, sqrtPriceLimitX96)` → 解析 `amountOut`
- **Pyth 集成**: `PriceFeed.getPriceNoOlderThan(60)` → 拿 SOL/USDC, USDC/USDT, WBNB/USDT 等 price → USD conversion

**R1 deliverable**:
- quote_snapshots.jsonl: `amount_in_raw, amount_out_raw, price_impact_pct, slippage_pct, fee_usd` 全部填**真实**值
- 53 池 × 6 notional × 12 ckpt = 3816 行, 全部非 0

### 1.3 real fee velocity proxy (volume + 实际 fee)

**当前 (R0)**: fee_velocity.jsonl `volume_proxy_usd=0, fee_capture_proxy_usd=0, sample_count=0`.

**R1 目标**: fee_velocity.jsonl 填**真实** volume + fee capture.

**实现**:
- **Volume source**: DexScreener API (per pool `volume.h24`, `volume.h6`, `volume.h1`) OR GeckoTerminal API OR on-chain swap event log subscription
- **Fee capture**: V3 fee capture = `liquidity * (feeGrowthGlobal - feeGrowthOutside)`; CPMM fee capture = `volume * fee_tier * lp_share` (lp_share 需 total_supply)
- **Cross-ckpt diff**: 跨 ckpt 24h window tokenId-based diff (需 tokenId schema, **不**需实际 tokenId, 可用 `liquidity_provider_proxy`)

**R1 deliverable**:
- fee_velocity.jsonl: `volume_proxy_usd, fee_capture_proxy_usd, sample_count` 全部填**真实**值
- 53 池 × 5 windows × 12 ckpt = 3180 行, 全部非 0

### 1.4 real volume source (DexScreener / on-chain)

**当前 (R0)**: `vol24h_proxy_usd` 来自 prior stage CSV (real value), **不**实时刷新.

**R1 目标**: per-ckpt 实时刷 volume (5 windows: 15m, 1h, 4h, 24h, 7d).

**实现**:
- **DexScreener API**: `https://api.dexscreener.com/latest/dex/pairs/solana/{pool_address}` → `volume.h24, volume.h6, volume.h1, volume.m15`
- **GeckoTerminal API**: `https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{pool_address}` → `volume_usd.h24`
- **On-chain swap event**: Solana `getSignaturesForAddress` + 解析 swap 指令; BSC `getLogs` + 解析 Swap event
- **Limitation**: DexScreener / GeckoTerminal 是中心化 indexer, 但 read-only, **不**算 paid RPC

**R1 deliverable**:
- per-ckpt vol24h_usd 实时刷新
- 5 windows 全部填**真实**值

### 1.5 real range / tick / bin liquidity (position state)

**当前 (R0)**: liquidity_distribution.jsonl `active_range_liquidity=0, near_active_liquidity=0, tick_spacing=null, bin_step=null`.

**R1 目标**: liquidity_distribution.jsonl 填**真实** range/tick/bin liquidity.

**实现**:
- **V3/CLMM**: 跨 `tickLower, tickUpper` 范围累积 liquidity 分布 (从 `ticks(net)` bitmap 读) → 计算 active_range / near_active / sparse
- **DLMM**: 跨 `bin_id` 范围累积 bin liquidity 分布 (从 dlmm-api / on-chain bin_array) → 计算 active_bin / near_active_bin
- **CPMM**: 单 bin (x*y=k), range=0, sparse=0, out_of_range_risk=N/A

**R1 deliverable**:
- liquidity_distribution.jsonl: 全部填**真实**值
- 53 池 × 12 ckpt = 636 行, 全部非 0

### 1.6 market regime classification (real-time price)

**当前 (R0)**: market_regime.jsonl `price_change_pct=0, realized_vol_pct=0, volume_to_tvl_pct=0, regime 标签静态分配`.

**R1 目标**: market_regime.jsonl 填**真实** 7d/24h lookback price change + realized vol.

**实现**:
- **Pyth 集成**: `PriceFeed.getPriceNoOlderThan(60)` → 拉 SOL, USDC, USDT, WBNB, cbBTC, JitoSOL, JTO, PYTH 等 price → 7d 滑动 window 算 price_change_pct + realized_vol_pct
- **CoinGecko fallback**: `https://api.coingecko.com/api/v3/coins/{id}/market_chart?vs_currency=usd&days=7` → 7d price history
- **Regime classifier**: per token_pair 7d price_change + realized_vol → uptrend / downtrend / sideways / high_volume_sideways / high_volatility_trend / incentive_period / low_volatility_stable

**R1 deliverable**:
- market_regime.jsonl: 全部填**真实**值
- 7 regimes × 12 ckpt = 84 行, 全部非 0 (or N/A → regime 标 "no_data" 不写入)

### 1.7 actual fee accrual schema (placeholder 维持)

**当前 (R0)**: actual_fee_accrual_placeholder.json 12 ckpt × 1 placeholder, 全部 null.

**R1 目标**: schema 维持 placeholder (r0 schema), **不** 填 actual data. **不** mint LP / add liquidity (freeze 仍 active).

**实现**:
- **Schema 维持**: 保持 current schema, **不** 改字段
- **数据维持**: 12 ckpt × 1 placeholder, 全部 null
- **r0_phase_status 维持**: "schema only, no records; r1 requires user-provided tokenId"
- **r0 → r1 transition explicit**: r1 完成后, freeze **仍** active for actual fee accrual, **不** mint

**R1 deliverable**:
- actual_fee_accrual_placeholder.json: 与 r0 **完全**一致 (schema only, all null)
- r1 docs 明确: "r1 = real data layer for fee/quote/regime/liquidity; r1 **不** = actual fee accrual"

## 2. R1 **不**做 (重要)

R1 严格遵守 freeze:
- ❌ **不** probe (can_run_probe_now 仍 false)
- ❌ **不** canary (tiny_canary_allowed 仍 'no')
- ❌ **不** live (live mode hard-disabled)
- ❌ **不** paper (paper mode not in spec)
- ❌ **不** 读 wallet / seed / keypair / signer
- ❌ **不** 发送 transaction
- ❌ **不** approve / mint / swap / bridge
- ❌ **不** 写 production positions
- ❌ **不** 覆盖 shadow 原始表
- ❌ **不** 接 paid RPC / paid indexer
- ❌ **不** mint 实际 LP NFT 仓位 (无 tokenId, freeze 仍 active)
- ❌ **不** actual fee accrual (schema 维持 placeholder)
- ❌ **不** actual tokenId (无 on-position)

**r1 范围**: real-time **read-only** data layer (RPC + price feed + volume indexer), **不** mint / **不** add liquidity / **不** actual fee.

## 3. R1 推荐任务名

**`LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`**

**任务名拆解**:
- `LP_LONG_HORIZON` — long horizon 任务系列
- `R1_REAL_DATA` — r0 → r1 upgrade, real data layer
- `OBSERVATION` — observation only, **不** probe / canary / live
- `UPGRADE_V1` — collector + adapter 升级, **不**新增 surface

**任务边界**:
- 升级 collector (scripts/lp_long_horizon_readonly_collector_v1.py) 加 real RPC + quote + volume + regime
- 升级 adapters (scripts/lp_long_horizon/adapters/) 走 real RPC call
- 升级 rpc_registry.py 加 retry / multi-endpoint / circuit breaker
- 升级 fee_estimation_basis (在 r1 doc) 写 "real data layer, all 6 dimensions non-zero"
- 升级 candidate_review (在 r1 doc) 重新跑 preflight, 输出 preflight_candidate_count > 0 (期望)
- 升级 market_regime (在 r1 doc) 用 real-time price feed classifier
- 升级 liquidity_distribution (在 r1 doc) 用 real range/tick/bin liquidity
- 升级 actual_fee_accrual **不**变 (schema only, freeze 仍 active)

**r1 完成后**:
- preflight_candidate_count: 0 → 可能 > 0 (期望; 但**仍**受 data_insufficient 影响)
- watchlist_count: 0 → 可能 > 0 (期望)
- data_insufficient_count: 53 → 应**显著**下降 (期望 ≤ 10, 取决于 RPC reachability + fee proxy 准确性)
- reject_count: 0 → 可能 > 0 (期望; tier_c hard reject applied)
- fee_proxy_only: true → false (期望; real data)
- actual_fee_data_available: false → false (维持, 因 freeze 仍 active)
- candidate_decision_reliable: false → 可能 true (期望; 但**仍**受 actual fee missing 影响)

**r1 后**:
- candidate_decision_reliable 仍**可能** false 因 actual fee 缺失
- actual_fee_data_available 仍**必须** false 因 freeze
- can_run_probe_now 仍 false
- tiny_canary_allowed 仍 'no'
- edge_proven 仍 'no'

**r1 → 实际 LP 决策**:
- 需 r2: freeze reopen + user mint 实际 LP NFT + 跨 24h+ ckpt tokenId-based diff
- r1 + freeze reopen → 才有 actual fee data
- r1 + freeze reopen + 24h+ tokenId diff → 才有 LP edge proven

## 4. R1 评估 (12h 后)

12h partial collector 跑完 (r0 phase PASS), R1 升级需:
- 1 stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- duration: 估计 2-3h (含 design + impl + test)
- output: 升级后 collector + 升级后 adapters + 升级后 r1 跑 12h 验证 (新 RUN_ID, 新 data_dir)
- r1 12h 跑完: preflight_candidate_count > 0, watchlist_count > 0, data_insufficient_count ≤ 10 (期望)
- r1 12h 跑完: **不** actual fee, **不** probe, **不** canary, **不** live, **不** paper

## 5. R1 风险

| Risk | Mitigation |
|---|---|
| Base RPC 仍 403 (paid blocked) | R1 在 solana + bsc 上跑, Base 仍 0 池 (但**不** blocker r1) |
| DexScreener API rate limit | 加 retry / circuit breaker / cache 5min |
| Pyth/CoinGecko API rate limit | 同上 |
| Meteora DLMM indexer 不可达 | R1 仍 16 池 DLMM TVL=0, 但**不** blocker r1 (因 tokenPair 真实) |
| BSC V2 0 pool (factory.getPair=0) | R1 仍 0 池 V2, **不** blocker r1 |
| r1 12h 跑出来 fee 仍太小 | 实事求是, **不** 翻 edge_proven=no → yes, **不** 翻 can_run_probe_now=false → true |

## 6. R1 后 next stage

| After R1 12h | Recommended next stage |
|---|---|
| R1 12h PASS, data_insufficient ≤ 10, preflight > 0, watchlist > 0 | `LP_LONG_HORIZON_R2_ACTUAL_FEE_ACCRUAL_UPGRADE_V1` (需 freeze reopen, user mint, tokenId) |
| R1 12h PASS, data_insufficient > 10, RPC reachability blocker | `LP_LONG_HORIZON_RPC_REACHABILITY_FIX_V1` (env change or wait for paid RPC approval) |
| R1 12h FAIL | `LP_LONG_HORIZON_R1_FAILURE_AUDIT_V1` (debug) |
| R1 12h PASS, freeze 仍 active, no actual fee data | `PAUSE_AUTOMATED_LP_PROBE_AND_COLLECT_LONGER_HORIZON_DATA` |

## 7. 锁定字段 (LOCKED, R1 期间仍不翻)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | actual fee 缺失, r1 不解决 |
| `global_lp_rejected` | `false` | r1 不 = reject |
| `actual_fee_data_available` | `false` | freeze, r1 不 = actual |
| `fee_proxy_only` | `true` (r0) → `false` (r1 期望) | r1 升级后填**真实** data |
| `candidate_decision_reliable` | `false` (r0) → `可能 true` (r1 期望) | r1 升级后**可能** reliable |
| `r1_upgrade_required` | `true` | 当前**必须**先 r1 |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
