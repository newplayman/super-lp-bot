# Stage C — 长期数据需求定义 (Long Horizon Data Requirements)

- stage: `LP_LONG_HORIZON_READONLY_DATA_PIPELINE_V1`
- run_id: `20260604_062324`

## 0. 目的

定义 7d / 14d / 30d 长期 baseline 采集的 6 类数据需求. 这是 read-only 数据 schema 蓝图,
不写 chain, 不发 tx, 不接 wallet. 给后续 R0 阶段长期跑 + R1/R2 阶段更深分析打基础.

## 1. 采集周期与最小 cell 数

| 周期 | 长度 | cell 数 (5 protocol × 6 notional × 7 regime) | 说明 |
|---|---|---|---|
| 7d baseline | 168h | 210 | 短基线, 验证 collector 通 |
| 14d baseline | 336h | 420 | 中基线, regime 切换可见 |
| 30d baseline | 720h | 900 | 长基线, 跨 regime 全覆盖 |

最小 cell 数 = protocol_count × notional_count × regime_count = 5 × 6 × 7 = 210 / 7d.
14d / 30d 等比放大 (实际是 7d 矩阵 × 时间窗, 每窗独立可分析).

## 2. 6 类数据需求

### 2.1 pool_snapshot

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| pool_address | string | yes | on-chain | pool 账户地址 |
| chain | enum | yes | config | solana / base / bsc |
| protocol | enum | yes | on-chain owner | meteora_dlmm / orca_whirlpool / raydium_clmm / raydium_cpmm / solana_stable |
| program_id | string | yes | on-chain | protocol program id |
| token_mint_a | string | yes | on-chain | base token mint |
| token_mint_b | string | yes | on-chain | quote token mint |
| token_symbol_a | string | yes | token list | base token symbol (e.g. SOL) |
| token_symbol_b | string | yes | token list | quote token symbol (e.g. USDC) |
| fee_tier_bps | int | yes | on-chain | 25 / 30 / 100 / 200 等 |
| reserve_a_raw | int | yes | on-chain | base token reserve (raw amount) |
| reserve_b_raw | int | yes | on-chain | quote token reserve (raw amount) |
| liquidity | int | yes | on-chain | V3 CL sqrt_price_x64 派生 / CPMM liquidity |
| active_tick | int | optional | on-chain | V3 CL 当前 tick |
| active_bin | int | optional | on-chain | DLMM 当前 bin |
| tvl_usd | float | yes | derived | reserve_a × price_a + reserve_b × price_b |
| snapshot_at | timestamp | yes | local | 本地采集时间 |

### 2.2 quote_snapshot

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| pool_address | string | yes | ref pool_snapshot | 关联 pool |
| notional_usd | enum | yes | config | 10 / 20 / 100 / 500 / 1000 / 2000 |
| quote_success | bool | yes | SDK swap_quote | quote 是否成功 |
| amount_in_raw | int | yes | derived | USD → token raw 转换 |
| amount_out_raw | int | yes | SDK | quote 输出 |
| price_impact_pct | float | yes | SDK | 滑点 |
| slippage_pct | float | yes | derived | (mid - out) / mid |
| fee_raw | int | yes | SDK | 估算 fee |
| fee_usd | float | yes | derived | fee × token price |
| error_code | string | optional | SDK | quote 失败原因 (e.g. 429 / liquidity_low) |
| quote_at | timestamp | yes | local | 本地采集时间 |

### 2.3 fee_velocity

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| pool_address | string | yes | ref pool_snapshot | 关联 pool |
| window | enum | yes | config | 15m / 1h / 6h / 24h / 7d rolling |
| volume_proxy_usd | float | yes | derived | quote 推导 fee × notional |
| fee_capture_proxy_usd | float | yes | derived | volume × fee_rate |
| volume_to_tvl_pct | float | yes | derived | volume / TVL |
| sample_count | int | yes | derived | 窗口内 sample 数 |
| window_end_at | timestamp | yes | local | 窗口结束时间 |

注: fee_velocity 在 R0 阶段是 **proxy** (用 quote + fee_rate 推导); R1 阶段才
升级为 **actual** (用 position tokenId + feeGrowth + collect fee).

### 2.4 liquidity_distribution

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| pool_address | string | yes | ref pool_snapshot | 关联 pool |
| active_range_liquidity | float | yes | on-chain | current tick 附近 ±1 tick 流动性 |
| near_active_liquidity | float | yes | on-chain | ±5 tick / ±5% bin |
| sparse_liquidity_warning | bool | yes | derived | near_active / active < 0.5 触发 |
| out_of_range_risk | float | yes | derived | 7d 价格 range 跨过 active tick 概率 (regime 派生) |
| tick_spacing | int | optional | on-chain | V3 CL tick spacing |
| bin_step | int | optional | on-chain | DLMM bin step |
| snapshot_at | timestamp | yes | local | 本地采集时间 |

### 2.5 market_regime

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| regime | enum | yes | classifier | 7 类之一 |
| lookback_days | int | yes | config | 7 / 30 |
| price_change_pct | float | yes | OHLC | 7d/30d 累计价格变化 |
| realized_vol_pct | float | yes | OHLC | 7d/30d 实现波动率 |
| volume_to_tvl_pct | float | yes | on-chain | 30d volume / TVL |
| incentive_active | bool | yes | protocol events | LM / bribe active |
| regime_at | timestamp | yes | local | regime 标识时间 |

7 regime 分类见 Stage F (regime classifier spec).

### 2.6 future_actual_fee_accrual_schema

| 字段 | 类型 | 必填 | 来源 | 说明 |
|---|---|---|---|---|
| token_id | string | yes | user / indexer | position NFT mint address |
| pool_address | string | yes | on-chain | position 所在 pool |
| entry_fee_growth_global | int | yes | on-chain | 进入时 pool 全局 feeGrowth |
| entry_fee_growth_a | int | yes | on-chain | 进入时 token_a 的 feeGrowthOutside |
| entry_fee_growth_b | int | yes | on-chain | 进入时 token_b 的 feeGrowthOutside |
| entry_tick_lower | int | yes | on-chain | LP 区间下界 |
| entry_tick_upper | int | yes | on-chain | LP 区间上界 |
| entry_at | timestamp | yes | on-chain | 进入时间 |
| exit_fee_growth_global | int | optional | on-chain | 退出时全局 feeGrowth (R1 阶段抓) |
| exit_fee_growth_a | int | optional | on-chain | 退出时 token_a feeGrowthOutside |
| exit_fee_growth_b | int | optional | on-chain | 退出时 token_b feeGrowthOutside |
| exit_tick_lower | int | optional | on-chain | 退出时下界 |
| exit_tick_upper | int | optional | on-chain | 退出时上界 |
| exit_at | timestamp | optional | on-chain | 退出时间 |
| tokens_owed_a_raw | int | yes | on-chain | 待收 token_a |
| tokens_owed_b_raw | int | yes | on-chain | 待收 token_b |
| actual_collected_a_raw | int | optional | collect event | 实际已 collect token_a (R1 阶段) |
| actual_collected_b_raw | int | optional | collect event | 实际已 collect token_b |
| actual_collected_at | timestamp | optional | on-chain | collect 时间 |
| actual_pnl_usd | float | optional | derived | entry vs exit + collected fee, USD 计价 |
| il_realized_pct | float | optional | derived | 真实 IL 实现 |
| il_actual_pct | float | optional | derived | 与 heuristic 对比 |

R0 阶段 schema 只在本地写 **placeholder** (token_id = null, 所有 actual 字段 null).
R1 阶段用户 / paid indexer 提供 token_id 后, 才能填 actual 字段.

## 3. 数据源映射 (read-only)

| 数据 | 数据源 | 是否需 paid |
|---|---|---|
| pool reserve / liquidity | on-chain getMultipleAccountsInfo | no (public RPC) |
| active tick / bin | on-chain | no |
| TVL (USD) | 派生 from reserve × token price | token price 用 public API (CoinGecko) |
| quote 10/20/100/500/1000/2000 | SDK swap_quote (read-only) | no (public RPC) |
| price 7d/30d change | CoinGecko / on-chain OHLC | no (public API) |
| realized vol | 派生 from OHLC | no |
| volume / TVL | on-chain indexer (DexScreener public) | no (rate limited) |
| incentive / LM | 协议 farm program events | partial (需 on-chain event log) |
| actual fee | user 提供 tokenId | yes (需 paid indexer) |

## 4. 采样策略 (smoke 阶段)

由于本任务只做 design + smoke, 不长期跑 daemon:
- protocol_count = 5
- pool_per_protocol = 3 (从已有 connector 已 verify 的池中选 3 个代表)
- notional_count = 6 (10 / 20 / 100 / 500 / 1000 / 2000)
- regime 标识 = 当前 regime (从 market_regime 表读)
- total cells (smoke) = 5 × 3 × 6 = 90

smoke 采样 1 次即停. 输出 reports/<RUN_DIR>/smoke_samples.json.

## 5. 字段锁定 vs build target

| 字段 | 状态 | 说明 |
|---|---|---|
| data_window | HIGH impact gap (上一阶段) | 本任务设计 7d/14d/30d schema, 解决 short window 局限 |
| fee_data | HIGH impact gap | R0 阶段 fee_velocity 是 proxy, R1 阶段才是 actual |
| il_lvr | HIGH impact gap | R0 阶段 out_of_range_risk 是 proxy, R1 阶段才是 actual playback |
| pool_selection | HIGH impact gap | R0 阶段只选 public feed, R3 阶段才加 incentive / vault |
| cost_data | MEDIUM impact gap | R0 阶段 cost 是 derived, R4 阶段才精确拆分 |
| capital_scale | MEDIUM impact gap | R0 阶段 notional 上限 2000 USD, R3 阶段才放大到 $1M+ |

## 6. 结论

6 类数据 schema 全部定义完成. R0 阶段 proxy 数据足够, R1/R3 阶段再升级到 actual /
incentive / vault. 本任务输出 schema (sql + jsonl + csv) 在 Stage E 给出.
