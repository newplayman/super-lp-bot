# Fee Estimation Review (12h Node Report Review)

- stage: `LP_LONG_HORIZON_PARTIAL_12H_NODE_REPORT_REVIEW_V1`
- run_id: `20260606_131323`
- branch: `feat/supabase-postgres-deployment`
- review_audited_at_utc: `2026-06-07T16:30:00Z`
- coverage_scope: `partial_solana_bsc_real_universe`

## 0. 一句话 (大白话)

12h 跑出来的 fee 数据**全部是 proxy** (代理/假数据), **不** 是 actual. 没有任何 LP 位置 tokenId, 没有任何 feeGrowthInside, 没有任何 tokensOwed, 没有任何 collected fee. 想用这数据决定"是否开 LP 仓位" = **完全不可行**. 只能用来验证 pipeline 跑通. 想有 actual fee data, 必须做 R1 升级 (需 freeze reopen + live RPC + 实际 mint 仓位).

## 1. 现在 fee 是什么状态 (大白话 Q&A)

### Q1: 当前 fee 是 proxy 还是 actual?

**Proxy**. 全部 fee_velocity.jsonl 行的 `smoke_placeholder=true`, `volume_proxy_usd=0`, `fee_capture_proxy_usd=0`, `sample_count=0`. 12 ckpt × 265 行 = 3180 行, **全部** 是 0. 这不是"fee 数字接近 0", 是"fee 数字**就**是 0, 因为没数据来源". r0_phase_status 字段 honest 写: "proxy (quote derived); r1 will upgrade to actual via tokenId".

**大白话**: 12h 跑出的 fee 数字是**摆样子的**, 0 × 53 池 × 5 windows × 12 ckpt = 0, **不**代表 12h 期间实际 fee 是 0. 这是 placeholder 标记, **不** 是真实值.

### Q2: 有没有 tokenId?

**没有**. actual_fee_accrual_placeholder.json 12 ckpt × 1 placeholder, 全部字段 `null`:
- `token_id: null`
- `pool_address: null`
- `entry_fee_growth_global: null`
- `entry_fee_growth_a: null`, `entry_fee_growth_b: null`
- `entry_tick_lower: null`, `entry_tick_upper: null`
- `entry_at: null`
- `exit_fee_growth_global: null`, `exit_fee_growth_a: null`, `exit_fee_growth_b: null`
- `exit_tick_lower: null`, `exit_tick_upper: null`
- `exit_at: null`
- `tokens_owed_a_raw: null`, `tokens_owed_b_raw: null`
- `actual_collected_a_raw: null`, `actual_collected_b_raw: null`
- `actual_collected_at: null`
- `actual_pnl_usd: null`
- `il_realized_pct: null`, `il_actual_pct: null`
- `r0_phase_status: "schema only, no records; r1 requires user-provided tokenId"`
- `smoke_placeholder: true`

**大白话**: 没有任何 LP NFT 仓位 mint, 所以**没有**任何 tokenId. 没有 tokenId = 算不出 feeGrowthInside 跨 ckpt diff = 算不出 actual fee. 这是**设计**, 因 freeze 不允许 mint / add liquidity.

### Q3: 是否有 feeGrowthInside?

**没有**. 见 Q2, 全部 null. feeGrowthInside0 / feeGrowthInside1 是 V3/CLMM pool 内部累计 fee 增长指标, **必须**有 on-position tokenId + 该 tokenId 对应的 tickLower/tickUpper 才能 query. r0 phase **不** query, **不** mint, **不**有.

### Q4: 是否有 tokensOwed?

**没有**. 见 Q2, 全部 null. tokensOwed0 / tokensOwed1 是 V3/CLMM position 累计未提取 fee 数量, **必须**有 on-position tokenId + 调用 `positions(tokenId)` 读取. r0 phase **不**读.

### Q5: 是否有 collected fee?

**没有**. 见 Q2, `actual_collected_a_raw: null`, `actual_collected_b_raw: null`, `actual_collected_at: null`. **必须**有 on-position tokenId + 实际调用 `decreaseLiquidity` / `collect` 才有. r0 phase **不**调用.

### Q6: V3/CLMM 的 range 宽窄如何影响 fee?

V3/CLMM 的 fee 捕获 = `feeGrowthInside0Last - feeGrowthInside0InsideLast` × `流动性` (在 [tickLower, tickUpper] 区间内). 范围越窄 → 流动性越集中 (假设同 LP 金额) → 单位流动性 fee 越高 → 但**如果价格出范围, fee = 0**. 范围越宽 → 流动性越分散 → 单位流动性 fee 越低 → 但**更不容易出范围**.

**12h r0 phase 不会**告诉你:
- 当前 tick 在哪
- tickLower / tickUpper 是什么
- 流动性集中在哪个 bin / tick
- 你的范围是否包含当前 tick
- 范围 fee 捕获是多少

**大白话**: r0 数据**不**回答 "V3/CLMM range 多宽合适" 这种问题, 因为连 tickLower / tickUpper / 真实 liquidity 都没有.

### Q7: DLMM bin coverage 如何影响 fee?

DLMM (Meteora) 是 bin-based 流动性, fee 捕获 = `bin_id` 在 [lower_bin_id, upper_bin_id] 区间内的流动性占比. 范围越窄 → bin 数越少 → 单 bin fee 越高 → 但**如果 active bin 出范围, fee = 0**.

**12h r0 phase 不会**告诉你:
- active_bin_id 是什么
- bin_step 是多少
- liquidity 在哪个 bin 集中
- 你的 range 包含哪些 bin
- bin fee 捕获是多少

**大白话**: r0 数据**不**回答 "DLMM bin coverage 多窄合适" 这种问题, 因为连 active_bin_id / bin_step / 真实 bin liquidity 都没有. (而且 Meteora DLMM 16 池的 TVL proxy 都是 0, 因 dlmm-api 在此 env 不可达.)

### Q8: CPMM fee share 如何估算?

CPMM (Raydium CPMM, PancakeSwap V2 等) 是 x*y=k 公式, fee 捕获 = `LP_share` × `pool_volume_24h` × `fee_tier`. LP_share = `your_lp_token_supply / total_lp_token_supply`.

**12h r0 phase 不会**告诉你:
- pool 实际 reserve0 / reserve1
- LP token 总 supply
- 你的 LP token 数量
- 你的 share 比例
- 24h 实际 volume
- 24h 实际 fee (USD)

**大白话**: r0 数据**不**回答 "CPMM LP share 多少" 这种问题, 因为连 reserve0/1 / total supply / volume 实际值都没有. (PancakeSwap V2 全部 0 池, factory.getPair=0.)

### Q9: 当前 R0 数据能不能用于参与决策?

**完全不能**. 12h r0 data = smoke_placeholder. 用于 LP 决策 = 用 0 算 EV = EV 永远 = 0 (或负, 因 IL/gas/rebalance/opportunity_cost 实际 > 0). 任何 LP 决策 (open position / increase / decrease / close / rebalance) 都**不**应该基于 r0 data.

**大白话**: r0 数据**不**是 "低质量 fee data", 是 "**没有** fee data, 只有 0". 用 0 决策 = 必然 "fee 不够, 不开" 误判 (因实际 fee 可能 > 0, 但 r0 测不出).

## 2. 12h r0 fee 数据明细 (大白话)

### 2.1 12h fee_velocity 数据 (53 池 × 5 windows × 12 ckpt = 3180 行)

| Window | 含义 | r0 实际值 |
|---|---|---|
| 15m | 过去 15 分钟 fee 捕获 | volume_proxy=0, fee_capture_proxy=0, sample_count=0 |
| 1h | 过去 1 小时 fee 捕获 | 同上 |
| 4h | 过去 4 小时 fee 捕获 | 同上 |
| 24h | 过去 24 小时 fee 捕获 | 同上 |
| 7d | 过去 7 天 fee 捕获 | 同上 |

**r0_phase_status 字段** (12 ckpt × 265 行, 全 3180 行 honest 标): `"proxy (quote derived); r1 will upgrade to actual via tokenId"`.

### 2.2 12h quote 数据 (53 池 × 6 notional × 12 ckpt = 3816 行)

| Notional | 含义 | r0 实际值 |
|---|---|---|
| 10 USD | 微小交易 quote | amount_in=0, amount_out=0, price_impact=0, slippage=0, fee=0 |
| 100 USD | 小额 | 同上 |
| 1k USD | 中等 | 同上 |
| 10k USD | 中大 | 同上 |
| 100k USD | 大额 | 同上 |
| 1M USD | 巨额 | 同上 |

**r0_phase_status 字段**: `smoke_placeholder=true`. (意思是 quote 行**有**schema, 但数字**全部**是 0, 因 no live QuoterV2 staticcall.)

### 2.3 12h pool_snapshots 数据 (53 池 × 12 ckpt = 636 行)

| Field | r0 实际值 |
|---|---|
| `tvl_proxy_usd` | 来自 prior stage CSV (real value) |
| `vol24h_proxy_usd` | 来自 prior stage CSV (real value) |
| `stable_classified` | 来自 prior stage CSV (real value) |
| `source_artifact` | 来自 prior stage CSV (real path) |
| `reserve_a_raw` | **0** (no live RPC) |
| `reserve_b_raw` | **0** (no live RPC) |
| `liquidity` | **0** (no live RPC) |
| `active_tick` | **null** (no live RPC) |
| `active_bin` | **null** (no live RPC) |
| `smoke_placeholder` | false (real address) but `r0_phase_status="real_pool_address_proxy_tvl_volume; no live RPC"` |

**大白话**: 53 池的 **address + TVL proxy + Vol24h proxy + stable_classified + source_artifact** 是**真实**的 (来自 prior stage connector CSVs), 但 **reserve / liquidity / tick / bin** 全部是 **0 / null** (因 no live RPC).

### 2.4 12h liquidity_distribution 数据 (53 池 × 12 ckpt = 636 行)

| Field | r0 实际值 |
|---|---|
| `active_range_liquidity` | 0.0 |
| `near_active_liquidity` | 0.0 |
| `sparse_liquidity_warning` | false (因 liquidity=0) |
| `out_of_range_risk` | 0.0 |
| `tick_spacing` | null (V3/CLMM) |
| `bin_step` | null (DLMM) |
| `smoke_placeholder` | true |

**r0_phase_status**: "schema only, no live tick/bin data". (意思是 liquidity_distribution schema **有**, 但数字**全部**是 0/null, 因无 tickLower / tickUpper / active_tick / active_bin.)

### 2.5 12h market_regime 数据 (7 regimes × 12 ckpt = 84 行)

| Regime | 含义 | r0 实际值 |
|---|---|---|
| uptrend | 7d lookback 上涨 | price_change_pct=0, realized_vol_pct=0, volume_to_tvl_pct=0, incentive_active=false, smoke_placeholder=true |
| downtrend | 7d lookback 下跌 | 同上 |
| sideways | 横盘 | 同上 |
| high_volume_sideways | 高量横盘 | 同上 |
| high_volatility_trend | 高波动趋势 | 同上 |
| incentive_period | 激励期 | 同上 |
| low_volatility_stable | 低波稳定 | 同上 |

**r0_phase_status**: "regime labels statically assigned per token_pair, not real-time market data". (意思是 regime **有** label, 但**不**是从 Pyth/CoinGecko 实时数据分类, 是**静态** per token_pair 分类.)

### 2.6 12h actual_fee_accrual 数据 (12 ckpt × 1 placeholder = 12 行)

**全部** null (见 Q2-Q5 详细). r0_phase_status: "schema only, no records; r1 requires user-provided tokenId".

## 3. 真实 fee 估算需要 (大白话)

**r0 → r1 升级需要 (按优先级)**:

1. **on-position tokenId** (必须, blocked by freeze)
   - freeze 不允许 mint LP NFT / add liquidity
   - 解 freeze → user 在 R1 实际开仓 → 拿 tokenId
   - 有了 tokenId → 可读 `positions(tokenId)` → 拿 tickLower/tickUpper/feeGrowthInsideLast/tokensOwed

2. **live RPC** (必须, blocked by env / freeze)
   - Solana: slot0/quoter_2/ticks_to_sqrt_price_x96 → 真实 reserve / liquidity / tick
   - BSC: slot0/quoter_2 → 真实 reserve / liquidity / tick
   - Base: 同 BSC (因 env 不可达, 需换 env or paid RPC, paid blocked by freeze)
   - Meteora DLMM: dlmm-api (env 不可达, 需换 indexer)

3. **real-time price feed** (Pyth/CoinGecko 集成, not yet wired)
   - market regime classification → real price_change_pct / realized_vol_pct
   - IL realized vs IL actual → entry/exit price diff × position value

4. **historical fee data** (跨 ckpt 24h+ tokenId-based diff)
   - actual fee_accrual = (feeGrowthInside0Last - feeGrowthInside0InsideLast) × liquidity
   - 跨 ckpt diff = actual fee captured in that window

5. **actual volume source** (DexScreener / GeckoTerminal / on-chain swap events)
   - volume_proxy_usd = on-chain swap event Σamount_in × price
   - volume_to_tvl_pct = volume_24h / tvl

**大白话**: r0 → r1 升级 = 5 件事: (1) 解 freeze 开仓拿 tokenId, (2) 解 RPC 限制拿真实 reserve, (3) 集成 price feed 拿真实 regime, (4) 跨 24h ckpt diff 算 actual fee, (5) 集成 volume indexer 算实际 volume. 5 件事**全部** blocked by freeze (或 env).

## 4. R0 数据能否进 probe / canary / live?

**绝对不能**. 三层防御:
1. **Data layer**: r0 fee = 0 → EV 算 = 0 → "EV<=0 拒绝" 误判 (因实际 EV 可能 > 0)
2. **Freeze**: `can_run_probe_now=false`, `tiny_canary_allowed="no"`, `send_hard_disable_still_active=true`
3. **Spec**: r0 phase 数据**不**是 LP 决策 input (per fee_estimation_basis.json disclosure)

**大白话**: 即便 freeze 解了, r0 数据**仍**不能进 probe, 因为 r0 = 0 算 EV = 必然拒绝. 必须先 r1 升级有 actual fee data, 再算 EV, 再进 probe.

## 5. R0 数据能否做 backtest?

**不能**. backtest 需 historical fee/IL/tvl/volume 数据, 同样 r0 = 0. backtest 用 0 fee = 必然 "fee 不够, 亏" 误判.

**大白话**: r0 data **不**是 "低质量历史数据", 是 "**没有**历史数据, 只有 0". backtest 没用.

## 6. R0 数据能否进 watchlist?

**不能**. watchlist 需 basic pool meta + recent fee trend + TVL trend. r0 fee trend = 0 × 12 ckpt = 0. TVL trend = static (因 reserve=0). watchlist 用 r0 = 必然空.

**大白话**: r0 data 填 watchlist = 必然空 watchlist (因全 0). watchlist 需 r1 actual data.

## 7. 锁定字段 (LOCKED)

| 字段 | 锁定值 | 锁定原因 |
|---|---|---|
| `can_run_probe_now` | `false` | r0 + freeze |
| `tiny_canary_allowed` | `"no"` | r0 + freeze |
| `edge_proven` | `"no"` | r0 phase data |
| `global_lp_rejected` | `false` | 12h 跑通 ≠ 拒绝 LP, 仍 r0 不够数据 |
| `actual_fee_data_available` | `false` | r0 placeholder |
| `fee_proxy_only` | `true` | r0 proxy only |
| `candidate_decision_reliable` | `false` | preflight=0, data_insufficient=53 |
| `preflight_candidate_count` | 0 | r0 |
| `watchlist_count` | 0 | r0 |
| `data_insufficient_count` | 53 | r0 |
| `r1_upgrade_required` | `true` | r0 → r1 mandatory before any LP decision |
| `wallet_or_tx_touched` | `false` | read-only |
| `transaction_sent` | `false` | no tx |
