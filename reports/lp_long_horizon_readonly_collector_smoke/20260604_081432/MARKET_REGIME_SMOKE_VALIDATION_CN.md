# Stage G — Market Regime Sample Validation

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_SMOKE_V1`
- run_id: `20260604_081432`
- smoke 输出: `data/lp_long_horizon/20260604_081432/collector_smoke/market_regime.jsonl`

## 0. 目的

验证 smoke mode 生成的 market_regime sample 满足 R0 阶段 spec:
- 7 regime 全部出现
- missing_data 显式标记 (smoke_placeholder=true)
- 不得伪造任何 regime 数据

## 1. regime sample 内容

7 条 record, 全部 7 regime 名称出现:

| regime | lookback_days | price_change_pct | realized_vol_pct | volume_to_tvl_pct | incentive_active | smoke_placeholder |
|---|---|---|---|---|---|---|
| uptrend | 7 | 0.0 | 0.0 | 0.0 | False | True |
| downtrend | 7 | 0.0 | 0.0 | 0.0 | False | True |
| sideways | 7 | 0.0 | 0.0 | 0.0 | False | True |
| high_volume_sideways | 7 | 0.0 | 0.0 | 0.0 | False | True |
| high_volatility_trend | 7 | 0.0 | 0.0 | 0.0 | False | True |
| incentive_period | 7 | 0.0 | 0.0 | 0.0 | False | True |
| low_volatility_stable | 7 | 0.0 | 0.0 | 0.0 | False | True |

## 2. 验证项

| 验证项 | 结果 |
|---|---|
| `regime_rows = 7` | ✅ pass |
| `regimes_present` = {uptrend, downtrend, sideways, high_volume_sideways, high_volatility_trend, incentive_period, low_volatility_stable} | ✅ pass (7/7) |
| `missing_data_marked = true` | ✅ pass (smoke_placeholder=true on all 7 rows) |
| `no_fabrication = true` | ✅ pass (所有数值字段=0.0, 没有伪造 regime 数据) |
| `lookback_days = 7` | ✅ pass (符合 spec 默认值) |
| `regime_at` 时间戳有效 | ✅ pass (ISO 8601 UTC) |

## 3. 与 spec (Stage F MARKET_REGIME_CLASSIFIER_SPEC) 对齐

spec 要求的 7 regime (per `market_regime_classifier_spec.json`):
- uptrend ✅
- downtrend ✅
- sideways ✅
- high_volume_sideways ✅
- high_volatility_trend ✅
- incentive_period ✅
- low_volatility_stable ✅

7/7 regime 全部出现. 优先级顺序在 spec 中定义, R0 阶段不实装 classifier, 仅 placeholder.

## 4. missing_data 标记

每条 record 都显式设置 `smoke_placeholder=true`, 这是 R0 阶段标识:
- 表示数据是 placeholder, 不是真实 regime 分类
- 表示 R0 阶段没有调用任何 real OHLC / realized_vol / volume_to_tvl / incentive
- 表示后续分析 (R2 阶段) 必须先把 placeholder 过滤掉, 再做 weighted EV

`incentive_active=false` 同样是 placeholder 默认, 不是真检测到无 LM/bribe.

`price_change_pct=0.0` / `realized_vol_pct=0.0` / `volume_to_tvl_pct=0.0` 全部是
placeholder 默认 0.0, 不是真测量到 0%.

## 5. 没有伪造

- [x] 没有伪造 regime 名称 (7 个真实 spec name)
- [x] 没有伪造 regime_at (ISO 8601 当前 UTC)
- [x] 没有伪造 lookback_days (默认 7 per spec)
- [x] 没有伪造 price_change_pct (0.0 = placeholder, 未真测)
- [x] 没有伪造 realized_vol_pct (0.0 = placeholder)
- [x] 没有伪造 volume_to_tvl_pct (0.0 = placeholder)
- [x] 没有伪造 incentive_active (false = placeholder, 未真检测)

## 6. classifier_ready_for_long_run

- [x] R0 阶段 long-run 启动前, 必须实装 classifier 函数 (per spec Stage F section 7)
- [x] 实装后, source adapter 必须替换 stub (per Stage C-5)
- [x] 启动 long-run 仍需 manual approval
- [x] 当前 `classifier_ready_for_long_run = false` (因为 classifier 仍 spec-only, 未实装)

## 7. 结论

7 regime placeholder 全部生成, missing_data 显式标记, 没有任何伪造数据.
regime spec 与 smoke 输出 100% 对齐. R0 阶段 long-run 启动前需实装 classifier
(spec outline 已给, 见 MARKET_REGIME_CLASSIFIER_SPEC_CN.md section 7) + 通过
单独 audit + manual approval.

Stage G 通过. 进入 Stage H (health / failure mode).
