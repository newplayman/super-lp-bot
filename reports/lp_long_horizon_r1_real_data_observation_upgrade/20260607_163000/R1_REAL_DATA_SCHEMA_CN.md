# R1 Real-Data Schema — 6 Dimensions

- stage: `LP_LONG_HORIZON_R1_REAL_DATA_OBSERVATION_UPGRADE_V1`
- run_id: `20260607_163000`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:55:00Z`

## 0. 一句话

R1 schema 重新定义 6 个 data file, 每个 file 字段从 R0 proxy/placeholder 升级到 R1 real-data-with-confidence, 字段包含 `confidence` (high/medium/low/unavailable) + `invalid_reason` (失败原因 honest 记录), **不** fallback to 0 placeholder. R1 schema 是 R0 schema 的 superset, R0 files (`pool_snapshots.jsonl` 等) **不** 修改, R1 输出新 files (`r1_pool_snapshot.jsonl` 等).

## 1. R1 schema 设计原则

### 1.1 R0 → R1 关键变化

| 维度 | R0 状态 | R1 状态 |
|---|---|---|
| 数据来源 | placeholder / static CSV / no RPC | live RPC + public API + on-chain |
| reserve_a/b | 0 | 真实 on-chain reserve (or confidence=unavailable with reason) |
| liquidity | 0 | 真实 V3/CLMM liquidity (or confidence=unavailable) |
| active_tick | null | 真实 current tick (or null with reason) |
| amount_in/out (quote) | 0 | 真实 QuoterV2 staticcall amount |
| price_impact_bps | 0.0 | 真实 price impact from quote |
| fee_capture_proxy_usd | 0.0 | 真实 on-chain volume × fee_tier |
| market_regime price_change_pct | 0.0 | 真实 7d Pyth/CoinGecko price change |
| smoke_placeholder flag | true (always) | **不** 用 smoke_placeholder; 改用 `confidence` + `invalid_reason` |
| Fallback to 0 | yes (R0 全部 0 fallback) | **不** fallback; confidence=unavailable + reason=... |

### 1.2 confidence 取值

- `high`: 真实 on-chain 数据, 多次验证 (e.g. slot0 + liquidity 跨 2+ calls)
- `medium`: 真实 on-chain 数据, 单次 call (e.g. 一次 getMultipleAccountsInfo)
- `low`: 部分 on-chain + 部分 proxy (e.g. tvl_proxy_usd 来自 CSV, reserve 来自 RPC)
- `unavailable`: 真实数据拿不到, **不** fallback to 0, **不** fallback to placeholder, 只 honest 记录 reason

### 1.3 invalid_reason 取值 (R1 honest failure modes)

- `rpc_unreachable`: RPC endpoint 不可达 (e.g. Base public RPC 403)
- `rpc_empty_response`: RPC 200 但 data=null/empty
- `rpc_rate_limited`: 429 (重试 3 次后放弃)
- `pool_address_invalid`: pool address 格式错误
- `adapter_not_implemented`: 协议 adapter 尚未实现
- `indexer_unreachable`: dlmm-api / DexScreener / GeckoTerminal 不可达
- `dexscreener_no_data`: DexScreener API 200 但 pair not found
- `pyth_no_price`: Pyth feed 无对应 token
- `coingecko_no_history`: CoinGecko 7d history 不足
- `insufficient_history`: 时间序列不足 (e.g. < 24h data)
- `cross_chain_skip`: 当前 chain 不在 R1 scope (e.g. Base 不可达 → skip 全部 Base 池)
- `token_not_resolved`: token mint / address 无法解析
- `unknown`: 其它未分类失败

## 2. R1 schema 6 dimensions

### 2.1 r1_pool_snapshot

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `chain` | str | solana / bsc / base | unchanged |
| `protocol` | str | orca_whirlpool / raydium_clmm / raydium_cpmm / meteora_dlmm / pancakeswap_v3 / pancakeswap_v2 / aerodrome_slipstream / aerodrome_classic / uniswap_v3 | unchanged |
| `pool_address` | str | pool on-chain address | unchanged |
| `token_pair` | str | SOL/USDC etc. | unchanged |
| `pool_type` | str | clmm / cpmm / dlmm | unchanged |
| `block_or_slot` | int | 当前 block (EVM) / slot (Solana) | **新增** |
| `timestamp_utc` | str ISO8601 | 数据采集时间 | unchanged |
| `reserve0` | str (decimal) | CPMM token0 reserve (raw) | R0=0 → R1=live or unavailable |
| `reserve1` | str (decimal) | CPMM token1 reserve (raw) | R0=0 → R1=live or unavailable |
| `liquidity` | str (decimal) | V3/CLMM liquidity (uint128 string) | R0=0 → R1=live or unavailable |
| `active_tick_or_bin` | int | V3/CLMM current tick (int24) or DLMM current bin_id (int32) | R0=null → R1=live or null with reason |
| `fee_tier_or_fee_bps` | int | V3 fee tier (e.g. 100 = 0.01%) or CPMM fee_bps (e.g. 25 = 0.25%) | unchanged |
| `tvl_usd_proxy` | float | TVL USD proxy (from prior stage CSV) | unchanged |
| `data_source` | str | rpc_slot0 / rpc_getReserves / rpc_getMultipleAccountsInfo / dlmm_api / dexscreener / coingecko / unavailable | **新增** |
| `confidence` | str | high / medium / low / unavailable | **新增** (替代 smoke_placeholder) |
| `invalid_reason` | str or null | 失败原因 (only when confidence=unavailable) | **新增** |

### 2.2 r1_quote_snapshot

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `pool_address` | str | pool on-chain address | unchanged |
| `notional_usd` | float | 测试 quote 规模 USD | unchanged |
| `token_in` | str | input token mint/address | unchanged |
| `token_out` | str | output token mint/address | unchanged |
| `amount_in` | str (decimal) | 实际 input amount (raw) | R0=0 → R1=live QuoterV2.staticcall(...) or unavailable |
| `amount_out` | str (decimal) | 实际 output amount (raw) | R0=0 → R1=live |
| `price_impact_bps` | float | 实际 price impact in bps | R0=0 → R1=live |
| `fee_bps` | int | 实际 fee bps (from QuoterV2 response) | R0=null → R1=live |
| `quote_success` | bool | quote 是否成功 | **新增** (替代 smoke_placeholder) |
| `quote_method` | str | quoter_v2_staticcall / whirlpool_quote_swap / raydium_clmm_quote / unavailable | **新增** |
| `confidence` | str | high / medium / low / unavailable | **新增** |
| `invalid_reason` | str or null | 失败原因 | **新增** |

### 2.3 r1_fee_velocity

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `pool_address` | str | pool on-chain address | unchanged |
| `window` | str | 15m / 1h / 4h / 24h / 7d | unchanged |
| `volume_usd` | float | 该 window 真实 volume USD (DexScreener / on-chain) | R0=0 → R1=live or unavailable |
| `fee_rate_bps` | int | pool fee rate (e.g. 4 = 0.04%) | unchanged |
| `estimated_fee_pool_usd` | float | pool-level fee = volume × fee_rate | R0=0 → R1=volume × fee_rate or unavailable |
| `source` | str | dexscreener / geckoterminal / on_chain_swap_event / unavailable | **新增** |
| `heuristic` | str | direct / derived / unavailable | **新增** (替代 r0_phase_status) |
| `confidence` | str | high / medium / low / unavailable | **新增** |
| `invalid_reason` | str or null | 失败原因 | **新增** |

### 2.4 r1_liquidity_distribution

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `pool_address` | str | pool on-chain address | unchanged |
| `range_type` | str | full_range (CPMM) / tick_range (V3/CLMM) / bin_range (DLMM) | **新增** |
| `bin_coverage` | str | N/A for CPMM / "±N ticks" for V3 / "M bins" for DLMM | **新增** |
| `active_liquidity` | float | active range/bin 内 liquidity | R0=0 → R1=live or unavailable |
| `near_active_liquidity` | float | near active (e.g. ±1%) liquidity | R0=0 → R1=live or unavailable |
| `in_range_liquidity_share_proxy` | float | active range/total 比例 (0-1) | R0=0 → R1=live or unavailable |
| `tick_or_bin_density` | float | liquidity per tick/bin (rough) | R0=0 → R1=live or unavailable |
| `sparse_warning` | bool | liquidity 是否 sparse (e.g. < 1% of TVL in active range) | R0=false → R1=live or false |
| `confidence` | str | high / medium / low / unavailable | **新增** |
| `invalid_reason` | str or null | 失败原因 | **新增** |

### 2.5 r1_market_regime

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `chain` | str | solana / bsc / base | **新增** (per chain) |
| `timestamp_utc` | str ISO8601 | 数据采集时间 | **新增** |
| `reference_asset` | str | 主要 reference asset (e.g. SOL, ETH, BNB) | **新增** (per chain) |
| `return_1h` | float | 1h return (decimal, e.g. 0.012 = 1.2%) | R0=0 → R1=live Pyth/CoinGecko |
| `return_6h` | float | 6h return | R0=0 → R1=live |
| `volatility_1h` | float | 1h realized volatility (annualized) | R0=0 → R1=live |
| `volatility_6h` | float | 6h realized volatility | R0=0 → R1=live |
| `regime_label` | str | uptrend / downtrend / sideways / high_volume_sideways / high_volatility_trend / incentive_period / low_volatility_stable / no_data | **新增** (新增 no_data 显式 label) |
| `confidence` | str | high / medium / low / unavailable | **新增** |
| `invalid_reason` | str or null | 失败原因 | **新增** |

### 2.6 r1_candidate_review

| 字段 | 类型 | 含义 | R0 → R1 |
|---|---|---|---|
| `pool_address` | str | pool on-chain address | unchanged |
| `quote_ready` | bool | r1_quote_snapshot 有 ≥1 high/medium confidence 行 | R0=false → R1=live |
| `fee_ready` | bool | r1_fee_velocity 有 ≥1 high/medium confidence 行 | R0=false → R1=live |
| `liquidity_ready` | bool | r1_liquidity_distribution 有 ≥1 high/medium confidence 行 | R0=false → R1=live |
| `regime_ready` | bool | r1_market_regime 覆盖此 chain | R0=false → R1=live |
| `ev_ready` | bool | quote_ready + fee_ready + liquidity_ready + regime_ready (但**不**需 tokenId) | R0=false → R1=可能 true |
| `preflight_candidate` | bool | 简化 preflight (R1 不做 full EV; 用 quote + fee + liquidity confidence proxy) | R0=false → R1=可能 true |
| `watchlist` | bool | basic pool meta + 至少 1 dimension high/medium confidence | R0=false → R1=可能 true |
| `data_insufficient` | bool | 4 dimensions 全部 unavailable/low | R0=true (53/53) → R1=应**显著**下降 |
| `reason` | str | 决策原因 (e.g. "quote_ready, fee_unavailable" / "all_unavailable" / "all_high_confidence") | **新增** |

## 3. R1 output files (per smoke run)

| File | Format | 用途 |
|---|---|---|
| `r1_pool_snapshot.csv` | CSV | human-readable, 53+ 池 |
| `r1_pool_snapshot.json` | JSON | machine-readable, {pools: [...], summary: {...}} |
| `r1_quote_snapshot.csv` | CSV | per pool × per notional (53 × 6 = 318 rows) |
| `r1_quote_snapshot.json` | JSON | same |
| `r1_fee_velocity.csv` | CSV | per pool × per window (53 × 5 = 265 rows) |
| `r1_fee_velocity.json` | JSON | same |
| `r1_liquidity_distribution.csv` | CSV | per pool (53 rows) |
| `r1_liquidity_distribution.json` | JSON | same |
| `r1_market_regime.csv` | CSV | per chain × per asset |
| `r1_market_regime.json` | JSON | same |
| `r1_candidate_review.csv` | CSV | per pool (53 rows) |
| `r1_candidate_review.json` | JSON | same |
| `r1_smoke_summary.json` | JSON | 顶层 summary (selected_pool_count, pool_snapshot_rows, ..., preflight_candidate_count, watchlist_count, data_insufficient_count, actual_fee_data_available=false, fee_proxy_only=true, no_wallet_tx_probe) |

## 4. R1 schema 与 R0 schema 关系

- R1 schema 是 R0 schema 的 **superset** (R0 schema 字段 + 新增 fields)
- R1 schema **不** 删除 R0 字段 (向后兼容)
- R1 schema 用 `confidence` + `invalid_reason` 替代 R0 `smoke_placeholder` + `r0_phase_status`
- R1 输出的 files 命名 `r1_*` (与 R0 `pool_snapshots.jsonl` 等区分)
- R0 files (12h data dir) **不** 修改

## 5. R1 锁定字段 (R1 smoke 期间)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `actual_fee_data_available` | `false` | R1 **不** mint, **不** actual fee |
| `fee_proxy_only` | `true` (R0) → 期望 R1=`false` if all 6 dimensions high confidence, but `actual_fee_data_available=false` LOCKED |
| `can_run_probe_now` | `false` | freeze active |
| `tiny_canary_allowed` | `"no"` | freeze active |
| `edge_proven` | `"no"` | R1 不 = edge proven |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |

**R1 期望**:
- preflight_candidate_count: 0 → 可能 > 0 (期望; 但**仍** 简化 preflight, **不** full EV)
- watchlist_count: 0 → 可能 > 0 (期望)
- data_insufficient_count: 53 → 应**显著**下降 (期望 ≤ 20)

**R1 不变**:
- actual_fee_data_available: false → false (LOCKED, R1 不 = actual fee)
- fee_proxy_only: true → 期望 false (but actual_fee_data_available 仍 false 因 freeze)
- candidate_decision_reliable: false → 可能 true (期望; 但**仍**受 actual fee missing 影响)
- can_run_probe_now / tiny_canary_allowed / edge_proven: 不变
