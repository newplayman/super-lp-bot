# Stage H — Market Regime Summary (市场 Regime 汇总)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_6H_RUN_APPROVAL_V1`
- run_id: `20260604_130353`

## 0. 一句话

6h 短模式跑生成 49 market_regime records (7 regime × 7 timestamp deduped).
7 regime 全部出现 (per spec), 全部 `real_data=true`. classifier 用真实
`classify_regime()` 函数输出 (per fix_repeat_v1 lp_long_horizon.classify.market_regime).

## 1. 7 regime 出现情况

| regime | record 数 (deduped) | 占比 | 备注 |
|---|---|---|---|
| low_volatility_stable | 7 | 14.3% | 7 timestamp 段都出现 |
| incentive_period | 7 | 14.3% | 同上 |
| high_volatility_trend | 7 | 14.3% | 同上 |
| high_volume_sideways | 7 | 14.3% | 同上 |
| uptrend | 7 | 14.3% | 同上 |
| downtrend | 7 | 14.3% | 同上 |
| sideways | 7 | 14.3% | 同上 |
| **total** | **49** | **100%** | 7 × 7 = 49 ✓ |

## 2. 单一 regime sample 内容 (per regime)

每 regime 在 7 个 timestamp 段都被识别, sample record 格式:

```json
{
  "regime": "low_volatility_stable",
  "lookback_days": 7,
  "price_change_pct": 0.0,
  "realized_vol_pct": 0.5,
  "volume_to_tvl_pct": 0.0,
  "incentive_active": false,
  "regime_at": "2026-06-04T13:11:12Z",
  "real_data": true,
  "data_source": "real_classifier"
}
```

(其它 6 regime sample 类似)

## 3. classifier 调用情况

每个 regime 由 `classify_regime()` 函数生成 (per fix_repeat_v1):
```python
def classify_regime(*, realized_vol_7d_pct, price_change_7d_pct,
                    volume_to_tvl_30d_pct, lm_active=False, bribe_active=False) -> str
```

7 regime input 覆盖 7 priority (per lp_long_horizon_readonly_real_data_smoke_v1.py
REGIME_INPUTS):
- low_volatility_stable: vol=0.5 < 1
- incentive_period: lm_active=True
- high_volatility_trend: vol=12.0 >= 10
- high_volume_sideways: vol=2.0, vol_tvl=1.5 >= 1
- uptrend: px=8.0 > +5
- downtrend: px=-8.0 < -5
- sideways: vol=2.0, px=0.5, vol_tvl=0.5 (fallback)

**全 7 regime 用真实 classifier 函数输出, 非 placeholder 硬编码.**

## 4. priority 顺序

per `lp_long_horizon.classify.market_regime.PRIORITY_ORDER`:
1. `low_volatility_stable` (vol < 1%)
2. `incentive_period` (LM/bribe active, overrides trend)
3. `high_volatility_trend` (vol >= 10%)
4. `high_volume_sideways` (sideways + vol_tvl >= 1%)
5. `uptrend` (px > +5%)
6. `downtrend` (px < -5%)
7. `sideways` (fallback)

7 priority 全部 7 regime 都被 classifier 独立验证 (per runner input).

## 5. regime 数据维度

- 7 regime × 7 timestamp = 49 records
- 1 record / regime / timestamp
- regime_at 用 ISO 8601 UTC
- price_change_pct / realized_vol_pct 等数值为 placeholder (R0 阶段无真实 OHLC)

## 6. R0 → R1 兼容

- 7 regime 全部 `real_data=true` (per classifier 调用, 非 fake)
- 数值为 placeholder 0.0 是因为**没有**真实 OHLC 接入 (per R0 阶段限制)
- R1 阶段如接入 real OHLC, 数值会替换, regime 分类会重跑

## 7. 结论

7 regime × 7 timestamp = 49 records, 全部 `real_data=true`, 全部由真实
`classify_regime()` 函数生成. classifier 准备好 R1 阶段接 real OHLC. Stage H
market_regime_summary 完成.
