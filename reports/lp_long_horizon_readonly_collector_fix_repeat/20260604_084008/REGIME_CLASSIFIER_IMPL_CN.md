# Stage G — Regime Classifier 实现 (Regime Classifier Implementation)

- stage: `LP_LONG_HORIZON_READONLY_COLLECTOR_FIX_REPEAT_V1`
- run_id: `20260604_084008`

## 0. 实现文件

- `scripts/lp_long_horizon/classify/market_regime.py`

## 1. classify_regime 函数 (核心)

```python
def classify_regime(*, realized_vol_7d_pct, price_change_7d_pct,
                    volume_to_tvl_30d_pct,
                    lm_active=False, bribe_active=False) -> str:
```

返回 7 regime 之一, 严格按 spec section 1 优先级:

1. `low_volatility_stable` — realized_vol_7d_pct < 1.0
2. `incentive_period` — lm_active OR bribe_active (覆盖 trend)
3. `high_volatility_trend` — realized_vol_7d_pct >= 10.0
4. `high_volume_sideways` — sideways + volume_to_tvl_30d_pct >= 1.0
5. `uptrend` — price_change_7d_pct > +5.0
6. `downtrend` — price_change_7d_pct < -5.0
7. `sideways` — fallback

## 2. 常量

```python
VOL_7D_LOW_THRESHOLD_PCT = 1.0
VOL_7D_HIGH_THRESHOLD_PCT = 10.0
PX_CHANGE_7D_UPTREND_THRESHOLD_PCT = 5.0
PX_CHANGE_7D_DOWNTREND_THRESHOLD_PCT = -5.0
VOL_TVL_30D_HIGH_VOLUME_THRESHOLD_PCT = 1.0
```

## 3. 辅助函数

- `is_valid_regime(name)` — 检查是否在 7 regime 内
- `regime_priority_index(name)` — 返回优先级 index (lower = higher)
- `build_market_regime_row(...)` — 构造 R0 schema 兼容 dict

## 4. 单元测试覆盖 (Stage L)

- `test_classify_low_vol_stable_priority`
- `test_classify_incentive_overrides_trend`
- `test_classify_high_vol_trend`
- `test_classify_high_volume_sideways`
- `test_classify_uptrend`
- `test_classify_downtrend`
- `test_classify_sideways_default`
- `test_classify_priority_5pct_boundary_uptrend`
- `test_classify_priority_5pct_boundary_downtrend`
- `test_classify_1pct_vol_boundary_low`
- `test_classify_10pct_vol_boundary_high`
- `test_classify_lm_active_overrides_downtrend`
- `test_classify_bribe_active_overrides_uptrend`
- `test_is_valid_regime`
- `test_regime_priority_index`

## 5. safety check (静态)

- [x] 0 wallet / signer / tx / mutation in real code
- [x] 0 bridge call
- [x] 0 production path
- [x] 0 shadow path
- [x] 0 daemon / cron / systemd
- [x] pure function, no I/O

## 6. 与 spec 对齐 (per MARKET_REGIME_CLASSIFIER_SPEC_CN.md)

| spec 字段 | 实际 | 状态 |
|---|---|---|
| 7 regime 名称 | 7 个常量 | ✅ |
| 优先级顺序 | PRIORITY_ORDER tuple | ✅ |
| 阈值 | 5 个常量 | ✅ |
| decision tree | classify_regime 函数体 | ✅ |
| 边界 1% / 5% / 10% | strict < / >= 行为 | ✅ |
| `unknown` placeholder | REGIME_UNKNOWN 常量 + 注释 | ✅ (未来 R1 用) |

## 7. 结论

7 regime classifier 实装完成, 严格按 spec. Stage G 通过. 进入 Stage H (SQLite storage).
