# Stage F — Smoke Output Schema Validation

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- smoke 输出目录: `data/lp_long_horizon/20260604_081432/collector_smoke/`

## 0. 目的

验证 smoke mode 7 个输出文件 (5 jsonl + 2 json) 的字段是否符合上一阶段 schema,
并确认无 secret / 无 production 写 / 无 shadow 覆盖.

## 1. 6 类 schema 验证

### 1.1 pool_snapshots (5 rows, 16 fields + smoke_placeholder)

期望字段 (per Stage E 1.1 schema): `pool_address, chain, protocol, program_id, token_mint_a, token_mint_b, token_symbol_a, token_symbol_b, fee_tier_bps, reserve_a_raw, reserve_b_raw, liquidity, active_tick, active_bin, tvl_usd, snapshot_at`

实际字段: `active_bin, active_tick, chain, fee_tier_bps, liquidity, pool_address, program_id, protocol, reserve_a_raw, reserve_b_raw, smoke_placeholder, snapshot_at, token_mint_a, token_mint_b, token_symbol_a, token_symbol_b, tvl_usd`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| pool_address | ✅ | pass |
| chain | ✅ | pass |
| protocol | ✅ | pass |
| program_id | ✅ | pass |
| token_mint_a | ✅ | pass |
| token_mint_b | ✅ | pass |
| token_symbol_a | ✅ | pass |
| token_symbol_b | ✅ | pass |
| fee_tier_bps | ✅ | pass |
| reserve_a_raw | ✅ | pass |
| reserve_b_raw | ✅ | pass |
| liquidity | ✅ | pass |
| active_tick | ✅ | pass (placeholder null) |
| active_bin | ✅ | pass (placeholder null) |
| tvl_usd | ✅ | pass |
| snapshot_at | ✅ | pass |

额外: `smoke_placeholder=true` (R0 阶段 marker, 与 schema 兼容)

### 1.2 quote_snapshots (30 rows, 11 fields + smoke_placeholder)

期望字段: `pool_address, notional_usd, quote_success, amount_in_raw, amount_out_raw, price_impact_pct, slippage_pct, fee_raw, fee_usd, error_code, quote_at`

实际字段: `amount_in_raw, amount_out_raw, error_code, fee_raw, fee_usd, notional_usd, pool_address, price_impact_pct, quote_at, quote_success, slippage_pct, smoke_placeholder`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| pool_address | ✅ | pass |
| notional_usd | ✅ | pass (10/20/100/500/1000/2000 6 个等级) |
| quote_success | ✅ | pass |
| amount_in_raw | ✅ | pass |
| amount_out_raw | ✅ | pass |
| price_impact_pct | ✅ | pass |
| slippage_pct | ✅ | pass |
| fee_raw | ✅ | pass |
| fee_usd | ✅ | pass |
| error_code | ✅ | pass (null in placeholder) |
| quote_at | ✅ | pass |

### 1.3 fee_velocity (25 rows, 7 fields + r0_phase_status + smoke_placeholder)

期望字段: `pool_address, window, volume_proxy_usd, fee_capture_proxy_usd, volume_to_tvl_pct, sample_count, window_end_at`

实际字段: `fee_capture_proxy_usd, pool_address, r0_phase_status, sample_count, smoke_placeholder, volume_proxy_usd, volume_to_tvl_pct, window, window_end_at`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| pool_address | ✅ | pass |
| window | ✅ | pass (15m/1h/6h/24h/7d 5 个 rolling) |
| volume_proxy_usd | ✅ | pass |
| fee_capture_proxy_usd | ✅ | pass |
| volume_to_tvl_pct | ✅ | pass |
| sample_count | ✅ | pass |
| window_end_at | ✅ | pass |

额外: `r0_phase_status=proxy (quote derived); r1 will upgrade to actual via tokenId` (R0→R1 升级 marker)

### 1.4 liquidity_distribution (5 rows, 8 fields + smoke_placeholder)

期望字段: `pool_address, active_range_liquidity, near_active_liquidity, sparse_liquidity_warning, out_of_range_risk, tick_spacing, bin_step, snapshot_at`

实际字段: `active_range_liquidity, bin_step, near_active_liquidity, out_of_range_risk, pool_address, smoke_placeholder, sparse_liquidity_warning, snapshot_at, tick_spacing`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| pool_address | ✅ | pass |
| active_range_liquidity | ✅ | pass |
| near_active_liquidity | ✅ | pass |
| sparse_liquidity_warning | ✅ | pass (false in placeholder) |
| out_of_range_risk | ✅ | pass |
| tick_spacing | ✅ | pass (null in placeholder, V3 CL) |
| bin_step | ✅ | pass (null in placeholder, DLMM) |
| snapshot_at | ✅ | pass |

### 1.5 market_regime (7 rows, 7 fields + smoke_placeholder)

期望字段: `regime, lookback_days, price_change_pct, realized_vol_pct, volume_to_tvl_pct, incentive_active, regime_at`

实际字段: `incentive_active, lookback_days, price_change_pct, realized_vol_pct, regime, regime_at, smoke_placeholder, volume_to_tvl_pct`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| regime | ✅ | pass (7 regime 全部出现) |
| lookback_days | ✅ | pass |
| price_change_pct | ✅ | pass |
| realized_vol_pct | ✅ | pass |
| volume_to_tvl_pct | ✅ | pass |
| incentive_active | ✅ | pass (false in placeholder) |
| regime_at | ✅ | pass |

### 1.6 future_actual_fee_accrual (1 placeholder, 23 fields + r0_phase_status + smoke_placeholder)

期望字段: 23 个 (entry / exit / collect / tokens_owed / derived 段)

实际字段: `actual_collected_a_raw, actual_collected_at, actual_collected_b_raw, actual_pnl_usd, entry_at, entry_fee_growth_a, entry_fee_growth_b, entry_fee_growth_global, entry_tick_lower, entry_tick_upper, exit_at, exit_fee_growth_a, exit_fee_growth_b, exit_fee_growth_global, exit_tick_lower, exit_tick_upper, il_actual_pct, il_realized_pct, pool_address, r0_phase_status, smoke_placeholder, token_id, tokens_owed_a_raw, tokens_owed_b_raw`

| 期望字段 | 实际存在 | 状态 |
|---|---|---|
| token_id | ✅ | pass (null in placeholder) |
| pool_address | ✅ | pass (null in placeholder) |
| entry_fee_growth_global | ✅ | pass |
| entry_fee_growth_a | ✅ | pass |
| entry_fee_growth_b | ✅ | pass |
| entry_tick_lower | ✅ | pass |
| entry_tick_upper | ✅ | pass |
| entry_at | ✅ | pass |
| exit_fee_growth_global | ✅ | pass |
| exit_fee_growth_a | ✅ | pass |
| exit_fee_growth_b | ✅ | pass |
| exit_tick_lower | ✅ | pass |
| exit_tick_upper | ✅ | pass |
| exit_at | ✅ | pass |
| tokens_owed_a_raw | ✅ | pass |
| tokens_owed_b_raw | ✅ | pass |
| actual_collected_a_raw | ✅ | pass |
| actual_collected_b_raw | ✅ | pass |
| actual_collected_at | ✅ | pass |
| actual_pnl_usd | ✅ | pass |
| il_realized_pct | ✅ | pass |
| il_actual_pct | ✅ | pass |

额外: `r0_phase_status=schema only, no records; r1 requires user-provided tokenId` (R0 阶段 schema-only marker)

## 2. secret / production / shadow 写检查

- [x] secret scan (`private_key|mnemonic|seed|keypair|wallet|api_key|secret|password|database_url|postgres_dsn|rpc_url`)
  在 `data/lp_long_horizon/20260604_081432/collector_smoke/` 中**唯一命中**是
  `smoke_summary.json` 的 `wallet_or_tx_touched: false` 字段名, 不是真实 secret.
- [x] production data path 检查:
  - `data/dryrun*` 不存在 ✅
  - `data/shadow*` 不存在 ✅
  - `data/live*` 不存在 ✅
  - `data/` 下只有 `lp_long_horizon/` 一个子目录 ✅
- [x] `migrations/` `cmd/` `internal/` `web/` `configs/` `reports/` 全部未触碰 ✅
- [x] shadow 原始表未覆盖 ✅ (shadow 表本身就不存在, 验证脚本也不会创建)

## 3. schema 验证结论

- [x] pool_snapshot schema ✅ pass
- [x] quote_snapshot schema ✅ pass
- [x] fee_velocity schema ✅ pass
- [x] liquidity_distribution schema ✅ pass
- [x] market_regime schema ✅ pass
- [x] actual_fee_accrual schema placeholder ✅ pass

6 类 schema 全部通过. smoke 输出 100% 符合 R0 阶段 placeholder 规范.
所有 record 是 placeholder (`smoke_placeholder=true` 或所有数值字段=0/null),
没有任何真实 on-chain 数据 / 真实 quote / 真实 fee 出现 (因为 source adapter 全部 stub).

## 4. R0→R1 兼容

smoke 输出的字段**完全兼容** R1 阶段 actual fee 升级:
- fee_velocity 多出 `r0_phase_status` 字段标识 R0 阶段, R1 阶段会替换为 actual 数据
- actual_fee placeholder 包含 23 个字段, R1 阶段填实际 tokenId + entry / exit / collect
- market_regime 7 regime placeholder 标识 R0 阶段 1 sample / day, R1 阶段用真实 OHLC 推导

也就是说, smoke 输出可直接被 R1 / R2 阶段脚本消费, 无需重新生成.

## 5. 结论

6 类 schema 全部通过, 无 secret 泄漏, 无 production / shadow 写, R0→R1 字段兼容.
Stage F 通过. 进入 Stage G (regime sample 验证).
